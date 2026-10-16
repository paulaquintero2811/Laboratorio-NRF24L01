from machine import Pin, SPI, I2C
import time
import ssd1306




# =========================================================
# OLED
# =========================================================


i2c = I2C(
    0,
    scl=Pin(5),
    sda=Pin(4),
    freq=400000
)


oled = ssd1306.SSD1306_I2C(
    128,
    64,
    i2c,
    addr=0x3C
)




# =========================================================
# BOTONES
# =========================================================


boton_parametro = Pin(10, Pin.IN, Pin.PULL_UP)
boton_valor = Pin(11, Pin.IN, Pin.PULL_UP)




# =========================================================
# LED
# =========================================================


led = Pin(12, Pin.OUT)
led.value(1)




# =========================================================
# SPI NRF24L01
# =========================================================


spi = SPI(
    0,
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=Pin(18),
    mosi=Pin(19),
    miso=Pin(16)
)


CE = Pin(17, Pin.OUT)
CSN = Pin(20, Pin.OUT)


CE.value(0)
CSN.value(1)




# =========================================================
# REGISTROS NRF24L01
# =========================================================


CONFIG = 0x00
EN_AA = 0x01
EN_RXADDR = 0x02
SETUP_AW = 0x03
SETUP_RETR = 0x04
RF_CH = 0x05
RF_SETUP = 0x06
STATUS = 0x07


RX_ADDR_P0 = 0x0A
TX_ADDR = 0x10
RX_PW_P0 = 0x11




# =========================================================
# COMANDOS NRF24L01
# =========================================================


W_REGISTER = 0x20
W_TX_PAYLOAD = 0xA0
FLUSH_TX = 0xE1
FLUSH_RX = 0xE2




# =========================================================
# CONFIGURACIÓN DEL SISTEMA
# =========================================================


# Canal inicial
canal = 76




# Velocidades disponibles
velocidades = [
    "250K",
    "1 Mbps",
    "2 Mbps"
]


velocidad_index = 1




# Potencias disponibles
potencias = [
    "-18 dBm",
    "-12 dBm",
    "-6 dBm",
    "0 dBm"
]


potencia_index = 3




# Mensajes
mensajes = [
    "EDIEM VALERO",
    "PAULA QUINTERO",
    "ALFABETO",
    "ALFABETO NUMERICO"
]


mensaje_index = 0




# Modos
modos = [
    "TX",
    "RX"
]


modo_index = 0




# Tipo de envío
envios = [
    "UNICO",
    "LOOP"
]


envio_index = 1




# =========================================================
# PARÁMETRO SELECCIONADO
# =========================================================
#
# 0 = Canal
# 1 = Velocidad
# 2 = Potencia
# 3 = Mensaje
# 4 = TX/RX
# 5 = UNICO/LOOP
# =========================================================


parametro = 0




# =========================================================
# VARIABLES DEL LED
# =========================================================


ultimo_parpadeo = time.ticks_ms()


estado_led_tx = False




# =========================================================
# FUNCIONES NRF24L01
# =========================================================


def escribir_registro(reg, valor):


    CSN.value(0)


    spi.write(bytes([W_REGISTER | reg]))
    spi.write(bytes([valor]))


    CSN.value(1)




def leer_registro(reg):


    CSN.value(0)


    spi.write(bytes([reg]))
    valor = spi.read(1)[0]


    CSN.value(1)


    return valor




def escribir_bytes(reg, datos):


    CSN.value(0)


    spi.write(bytes([W_REGISTER | reg]))
    spi.write(bytes(datos))


    CSN.value(1)




def comando(com):


    CSN.value(0)


    spi.write(bytes([com]))


    CSN.value(1)




# =========================================================
# CONFIGURAR VELOCIDAD Y POTENCIA
# =========================================================


def configurar_rf_setup():


    # -------------------------
    # VELOCIDAD
    # -------------------------


    if velocidad_index == 0:


        # 250 kbps
        velocidad_bits = 0x20


    elif velocidad_index == 1:


        # 1 Mbps
        velocidad_bits = 0x00


    else:


        # 2 Mbps
        velocidad_bits = 0x08




    # -------------------------
    # POTENCIA
    # -------------------------


    if potencia_index == 0:


        # -18 dBm
        potencia_bits = 0x00


    elif potencia_index == 1:


        # -12 dBm
        potencia_bits = 0x02


    elif potencia_index == 2:


        # -6 dBm
        potencia_bits = 0x04


    else:


        # 0 dBm
        potencia_bits = 0x06




    escribir_registro(
        RF_SETUP,
        velocidad_bits | potencia_bits
    )




# =========================================================
# CONFIGURAR NRF24L01
# =========================================================


def configurar_nrf():


    CE.value(0)


    # Power down
    escribir_registro(CONFIG, 0x00)


    time.sleep_ms(2)




    # Auto ACK desactivado
    escribir_registro(
        EN_AA,
        0x00
    )




    # Pipe 0
    escribir_registro(
        EN_RXADDR,
        0x01
    )




    # Dirección de 5 bytes
    escribir_registro(
        SETUP_AW,
        0x03
    )




    # Sin retransmisiones
    escribir_registro(
        SETUP_RETR,
        0x00
    )




    # -------------------------
    # CANAL
    # -------------------------


    escribir_registro(
        RF_CH,
        canal
    )




    # -------------------------
    # VELOCIDAD Y POTENCIA
    # -------------------------


    configurar_rf_setup()




    # Payload máximo
    escribir_registro(
        RX_PW_P0,
        32
    )




    # -------------------------
    # DIRECCIÓN
    # -------------------------


    direccion = b"RADIO"


    escribir_bytes(
        TX_ADDR,
        direccion
    )


    escribir_bytes(
        RX_ADDR_P0,
        direccion
    )




    # -------------------------
    # LIMPIAR FIFO
    # -------------------------


    comando(FLUSH_TX)
    comando(FLUSH_RX)




    # Limpiar banderas
    escribir_registro(
        STATUS,
        0x70
    )




    # -------------------------
    # TX / RX
    # -------------------------


    if modos[modo_index] == "TX":


        # PWR_UP = 1
        # PRIM_RX = 0
        escribir_registro(
            CONFIG,
            0x02
        )


    else:


        # PWR_UP = 1
        # PRIM_RX = 1
        escribir_registro(
            CONFIG,
            0x03
        )




    time.sleep_ms(5)




# =========================================================
# TRANSMITIR MENSAJE
# =========================================================


def transmitir(mensaje):


    datos = mensaje.encode()




    # Máximo 32 bytes
    if len(datos) > 32:


        datos = datos[:32]




    # Completar hasta 32 bytes
    datos = datos + bytes(
        32 - len(datos)
    )




    # Limpiar FIFO TX
    comando(FLUSH_TX)




    # Cargar payload
    CSN.value(0)


    spi.write(
        bytes([W_TX_PAYLOAD])
    )


    spi.write(datos)


    CSN.value(1)




    # Pulso CE
    CE.value(1)


    time.sleep_us(20)


    CE.value(0)




# =========================================================
# PARPADEO MANUAL
# =========================================================


def parpadeo(cantidad):


    for i in range(cantidad):


        led.value(0)


        time.sleep_ms(80)


        led.value(1)


        time.sleep_ms(80)




# =========================================================
# FRECUENCIA RF
# =========================================================


def calcular_frecuencia():


    return 2400 + canal




# =========================================================
# MOSTRAR PANTALLA PRINCIPAL
# =========================================================


def mostrar_principal():


    oled.fill(0)


    oled.text(
        "NRF24L01",
        0,
        0
    )


    oled.text(
        "Canal: " + str(canal),
        0,
        12
    )


    oled.text(
        "Vel: " + velocidades[velocidad_index],
        0,
        22
    )


    oled.text(
        "Pot: " + potencias[potencia_index],
        0,
        32
    )


    oled.text(
        "Modo: " + modos[modo_index],
        0,
        42
    )


    oled.text(
        "Env: " + envios[envio_index],
        0,
        52
    )


    oled.show()




# =========================================================
# MOSTRAR PARÁMETRO
# =========================================================


def mostrar_parametro():


    oled.fill(0)




    # -------------------------
    # CANAL
    # -------------------------


    if parametro == 0:


        oled.text(
            "SELECCION",
            0,
            0
        )


        oled.text(
            "CANAL",
            0,
            20
        )


        oled.text(
            str(canal),
            0,
            40
        )




    # -------------------------
    # VELOCIDAD
    # -------------------------


    elif parametro == 1:


        oled.text(
            "SELECCION",
            0,
            0
        )


        oled.text(
            "VELOCIDAD",
            0,
            20
        )


        oled.text(
            velocidades[velocidad_index],
            0,
            40
        )




    # -------------------------
    # POTENCIA
    # -------------------------


    elif parametro == 2:


        oled.text(
            "SELECCION",
            0,
            0
        )


        oled.text(
            "POTENCIA",
            0,
            20
        )


        oled.text(
            potencias[potencia_index],
            0,
            40
        )




    # -------------------------
    # MENSAJE
    # -------------------------


    elif parametro == 3:


        oled.text(
            "MENSAJE",
            0,
            0
        )


        mensaje = mensajes[mensaje_index]


        oled.text(
            mensaje[:16],
            0,
            20
        )


        if len(mensaje) > 16:


            oled.text(
                mensaje[16:32],
                0,
                32
            )


        oled.text(
            str(mensaje_index + 1)
            + "/"
            + str(len(mensajes)),
            0,
            52
        )




    # -------------------------
    # TX / RX
    # -------------------------


    elif parametro == 4:


        oled.text(
            "SELECCION",
            0,
            0
        )


        oled.text(
            "MODO",
            0,
            20
        )


        oled.text(
            modos[modo_index],
            0,
            40
        )




    # -------------------------
    # UNICO / LOOP
    # -------------------------


    elif parametro == 5:


        oled.text(
            "TIPO ENVIO",
            0,
            0
        )


        oled.text(
            envios[envio_index],
            0,
            25
        )




    oled.show()




# =========================================================
# CAMBIAR CONFIGURACIÓN
# =========================================================


def actualizar_nrf():


    print()
    print("Actualizando NRF24L01...")


    configurar_nrf()


    print(
        "Canal:",
        canal
    )


    print(
        "Frecuencia:",
        calcular_frecuencia(),
        "MHz"
    )


    print(
        "Velocidad:",
        velocidades[velocidad_index]
    )


    print(
        "Potencia:",
        potencias[potencia_index]
    )


    print(
        "Modo:",
        modos[modo_index]
    )


    print(
        "Envio:",
        envios[envio_index]
    )


    print(
        "Mensaje:",
        mensajes[mensaje_index]
    )


    print()




# =========================================================
# CAMBIAR VALOR
# =========================================================


def cambiar_valor():


    global canal
    global velocidad_index
    global potencia_index
    global mensaje_index
    global modo_index
    global envio_index




    # -------------------------
    # CANAL
    # -------------------------


    if parametro == 0:


        canal += 1


        if canal > 80:


            canal = 70




    # -------------------------
    # VELOCIDAD
    # -------------------------


    elif parametro == 1:


        velocidad_index += 1


        if velocidad_index >= len(velocidades):


            velocidad_index = 0




    # -------------------------
    # POTENCIA
    # -------------------------


    elif parametro == 2:


        potencia_index += 1


        if potencia_index >= len(potencias):


            potencia_index = 0




    # -------------------------
    # MENSAJE
    # -------------------------


    elif parametro == 3:


        mensaje_index += 1


        if mensaje_index >= len(mensajes):


            mensaje_index = 0




    # -------------------------
    # TX / RX
    # -------------------------


    elif parametro == 4:


        modo_index += 1


        if modo_index >= len(modos):


            modo_index = 0




    # -------------------------
    # UNICO / LOOP
    # -------------------------


    elif parametro == 5:


        envio_index += 1


        if envio_index >= len(envios):


            envio_index = 0




    # Actualizar NRF
    actualizar_nrf()




# =========================================================
# INICIALIZACIÓN
# =========================================================


print()
print("================================")
print("       SISTEMA NRF24L01")
print("================================")


actualizar_nrf()


mostrar_principal()


time.sleep_ms(1000)




# =========================================================
# ESTADO DE BOTONES
# =========================================================


ultimo_boton_parametro = 1
ultimo_boton_valor = 1




# =========================================================
# CONTROL DEL LED
# =========================================================


ultimo_led = time.ticks_ms()


estado_led = 0




# =========================================================
# CONTROL DE ENVÍO ÚNICO
# =========================================================


ultimo_mensaje_enviado = -1




# =========================================================
# LOOP PRINCIPAL
# =========================================================


while True:


    # =====================================================
    # LEER BOTONES
    # =====================================================


    estado_parametro = boton_parametro.value()


    estado_valor = boton_valor.value()




    # =====================================================
    # BOTÓN 1
    # SELECCIONAR PARÁMETRO
    # =====================================================


    if (
        estado_parametro == 0
        and ultimo_boton_parametro == 1
    ):


        parametro += 1


        if parametro > 5:


            parametro = 0




        print(
            "Parametro seleccionado:",
            parametro + 1
        )




        parpadeo(1)


        mostrar_parametro()


        time.sleep_ms(200)




    # =====================================================
    # BOTÓN 2
    # CAMBIAR VALOR
    # =====================================================


    if (
        estado_valor == 0
        and ultimo_boton_valor == 1
    ):


        cambiar_valor()


        print(
            "Valor cambiado"
        )




        parpadeo(2)


        mostrar_parametro()


        time.sleep_ms(200)




    ultimo_boton_parametro = estado_parametro


    ultimo_boton_valor = estado_valor




    # =====================================================
    # MODO TX
    # =====================================================


    if modos[modo_index] == "TX":


        mensaje_actual = mensajes[mensaje_index]




        # =================================================
        # LOOP
        # =================================================


        if envios[envio_index] == "LOOP":


            # Transmitir
            transmitir(
                mensaje_actual
            )




            # -------------------------------------------------
            # LED
            #
            # El NRF transmite cada 1 ms.
            # El LED cambia cada 100 ms para que sea visible.
            # -------------------------------------------------


            ahora = time.ticks_ms()


            if time.ticks_diff(
                ahora,
                ultimo_led
            ) >= 100:


                estado_led = not estado_led


                led.value(
                    estado_led
                )


                ultimo_led = ahora




            # Mantener transmisión rápida
            time.sleep_ms(1)




        # =================================================
        # UNICO
        # =================================================


        else:


            # El LED queda apagado mientras espera
            led.value(0)




            # No repetir automáticamente
            #
            # El envío único se realiza cuando se cambia
            # nuevamente el parámetro de envío.
            #
            # Para realizar una prueba de UNICO se puede
            # cambiar a LOOP y regresar a UNICO.




    # =====================================================
    # MODO RX
    # =====================================================


    else:


        # En RX
        CE.value(1)


        # LED fijo indicando RX
        led.value(1)


        time.sleep_ms(1)


        CE.value(0)