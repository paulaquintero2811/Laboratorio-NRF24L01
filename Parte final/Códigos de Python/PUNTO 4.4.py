
from machine import Pin, SPI, I2C
import time
import ssd1306

# =========================================================
# OLED
# =========================================================

i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400000)
oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)

# =========================================================
# BOTONES Y LED
# =========================================================

boton_parametro = Pin(10, Pin.IN, Pin.PULL_UP)
boton_valor = Pin(11, Pin.IN, Pin.PULL_UP)
led = Pin(12, Pin.OUT)
led.value(0)

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
# REGISTROS Y COMANDOS
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

W_REGISTER = 0x20
W_TX_PAYLOAD = 0xA0
FLUSH_TX = 0xE1
FLUSH_RX = 0xE2
NOP = 0xFF

# =========================================================
# CONFIGURACIÓN INICIAL
# =========================================================

canal = 71

velocidades = ["250K", "1 Mbps", "2 Mbps"]
velocidad_index = 1

potencias = ["-18 dBm", "-12 dBm", "-6 dBm", "0 dBm"]
potencia_index = 3

mensajes = [
    "EDIEM VALERO",
    "PAULA QUINTERO",
    "ALFABETO",
    "ALFABETO NUMERICO"
]
mensaje_index = 0

modos = ["TX", "RX"]
modo_index = 0

envios = ["UNICO", "LOOP"]
envio_index = 1

# 0 Canal, 1 Velocidad, 2 Potencia,
# 3 Mensaje, 4 TX/RX, 5 UNICO/LOOP
parametro = 0

ultimo_boton_parametro = 1
ultimo_boton_valor = 1
ultimo_led = time.ticks_ms()
estado_led = False
ultimo_unico = False

# =========================================================
# FUNCIONES DE REGISTROS
# =========================================================

def escribir_registro(reg, valor):
    CSN.value(0)
    spi.write(bytes([W_REGISTER | reg, valor & 0xFF]))
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
    spi.write(datos)
    CSN.value(1)


def comando(com):
    CSN.value(0)
    spi.write(bytes([com]))
    CSN.value(1)


def leer_estado():
    CSN.value(0)
    estado = spi.write_readinto(
        bytearray([NOP]),
        bytearray(1)
    )
    # Se realiza una lectura separada para obtener el estado
    CSN.value(1)

    CSN.value(0)
    rx = bytearray(1)
    spi.write_readinto(bytearray([NOP]), rx)
    CSN.value(1)
    return rx[0]


# =========================================================
# VELOCIDAD Y POTENCIA
# =========================================================

def configurar_rf_setup():
    if velocidad_index == 0:
        velocidad_bits = 0x20
    elif velocidad_index == 1:
        velocidad_bits = 0x00
    else:
        velocidad_bits = 0x08

    if potencia_index == 0:
        potencia_bits = 0x00
    elif potencia_index == 1:
        potencia_bits = 0x02
    elif potencia_index == 2:
        potencia_bits = 0x04
    else:
        potencia_bits = 0x06

    escribir_registro(RF_SETUP, velocidad_bits | potencia_bits)


# =========================================================
# CONFIGURAR NRF24L01
# =========================================================

def configurar_nrf():
    CE.value(0)

    escribir_registro(CONFIG, 0x00)
    time.sleep_ms(2)

    escribir_registro(EN_AA, 0x00)
    escribir_registro(EN_RXADDR, 0x01)
    escribir_registro(SETUP_AW, 0x03)
    escribir_registro(SETUP_RETR, 0x00)

    escribir_registro(RF_CH, canal)
    configurar_rf_setup()
    escribir_registro(RX_PW_P0, 32)

    direccion = b"RADIO"
    escribir_bytes(TX_ADDR, direccion)
    escribir_bytes(RX_ADDR_P0, direccion)

    comando(FLUSH_TX)
    comando(FLUSH_RX)
    escribir_registro(STATUS, 0x70)

    if modos[modo_index] == "TX":
        escribir_registro(CONFIG, 0x02)
    else:
        escribir_registro(CONFIG, 0x03)

    time.sleep_ms(2)


# =========================================================
# TRANSMITIR UN PAQUETE DE 32 BYTES
# =========================================================

def transmitir(mensaje):
    datos = mensaje.encode()[:32]
    datos += bytes(32 - len(datos))

    comando(FLUSH_TX)
    escribir_registro(STATUS, 0x70)

    CSN.value(0)
    spi.write(bytes([W_TX_PAYLOAD]))
    spi.write(datos)
    CSN.value(1)

    CE.value(1)
    time.sleep_us(15)
    CE.value(0)

    inicio = time.ticks_ms()

    while time.ticks_diff(time.ticks_ms(), inicio) < 5:
        estado = leer_estado()

        if estado & 0x20:  # TX_DS
            escribir_registro(STATUS, 0x20)
            return True

        if estado & 0x10:  # MAX_RT
            escribir_registro(STATUS, 0x10)
            comando(FLUSH_TX)
            return False

    comando(FLUSH_TX)
    escribir_registro(STATUS, 0x70)
    return False


# =========================================================
# LED
# =========================================================

def parpadeo(cantidad):
    for _ in range(cantidad):
        led.value(0)
        time.sleep_ms(60)
        led.value(1)
        time.sleep_ms(60)


# =========================================================
# FRECUENCIA
# =========================================================

def calcular_frecuencia():
    return 2400 + canal


# =========================================================
# PANTALLA PRINCIPAL
# =========================================================

def mostrar_principal():
    oled.fill(0)
    oled.text("NRF24L01", 0, 0)
    oled.text("Canal: " + str(canal), 0, 12)
    oled.text("Vel: " + velocidades[velocidad_index], 0, 22)
    oled.text("Pot: " + potencias[potencia_index], 0, 32)
    oled.text("Modo: " + modos[modo_index], 0, 42)
    oled.text("Env: " + envios[envio_index], 0, 52)
    oled.show()


# =========================================================
# PANTALLA DE SELECCIÓN
# =========================================================

def mostrar_parametro():
    oled.fill(0)
    oled.text("SELECCION", 0, 0)

    if parametro == 0:
        oled.text("CANAL", 0, 20)
        oled.text(str(canal), 0, 40)

    elif parametro == 1:
        oled.text("VELOCIDAD", 0, 20)
        oled.text(velocidades[velocidad_index], 0, 40)

    elif parametro == 2:
        oled.text("POTENCIA", 0, 20)
        oled.text(potencias[potencia_index], 0, 40)

    elif parametro == 3:
        oled.text("MENSAJE", 0, 20)
        oled.text(mensajes[mensaje_index][:16], 0, 36)
        oled.text(str(mensaje_index + 1) + "/4", 0, 52)

    elif parametro == 4:
        oled.text("MODO", 0, 20)
        oled.text(modos[modo_index], 0, 40)

    elif parametro == 5:
        oled.text("TIPO ENVIO", 0, 20)
        oled.text(envios[envio_index], 0, 40)

    oled.show()


# =========================================================
# ACTUALIZAR CONFIGURACIÓN
# =========================================================

def actualizar_nrf():
    configurar_nrf()

    print("Canal:", canal)
    print("Frecuencia:", calcular_frecuencia(), "MHz")
    print("Velocidad:", velocidades[velocidad_index])
    print("Potencia:", potencias[potencia_index])
    print("Modo:", modos[modo_index])
    print("Envio:", envios[envio_index])
    print("Mensaje:", mensajes[mensaje_index])


# =========================================================
# CAMBIAR VALOR
# =========================================================

def cambiar_valor():
    global canal, velocidad_index, potencia_index
    global mensaje_index, modo_index, envio_index

    if parametro == 0:
        canal += 1
        if canal > 80:
            canal = 70

    elif parametro == 1:
        velocidad_index = (velocidad_index + 1) % len(velocidades)

    elif parametro == 2:
        potencia_index = (potencia_index + 1) % len(potencias)

    elif parametro == 3:
        mensaje_index = (mensaje_index + 1) % len(mensajes)

    elif parametro == 4:
        modo_index = (modo_index + 1) % len(modos)

    elif parametro == 5:
        envio_index = (envio_index + 1) % len(envios)

    actualizar_nrf()
    mostrar_principal()


# =========================================================
# INICIALIZACIÓN
# =========================================================

print("=== NRF24L01 - PRUEBA 4.4 ===")
actualizar_nrf()
mostrar_principal()

# =========================================================
# BUCLE PRINCIPAL
# =========================================================

while True:
    estado_parametro = boton_parametro.value()
    estado_valor = boton_valor.value()

    # Botón 1: seleccionar parámetro
    if estado_parametro == 0 and ultimo_boton_parametro == 1:
        parametro = (parametro + 1) % 6
        parpadeo(1)
        mostrar_parametro()
        time.sleep_ms(180)

    # Botón 2: cambiar valor
    if estado_valor == 0 and ultimo_boton_valor == 1:
        cambiar_valor()
        parpadeo(1)
        mostrar_parametro()
        time.sleep_ms(180)

    ultimo_boton_parametro = estado_parametro
    ultimo_boton_valor = estado_valor

    # Transmisor
    if modos[modo_index] == "TX":
        if envios[envio_index] == "LOOP":
            transmitir(mensajes[mensaje_index])

            ahora = time.ticks_ms()
            if time.ticks_diff(ahora, ultimo_led) >= 100:
                estado_led = not estado_led
                led.value(estado_led)
                ultimo_led = ahora
        else:
            led.value(0)

    # Receptor: mantener el NRF escuchando
    else:
        CE.value(1)
        led.value(1)
