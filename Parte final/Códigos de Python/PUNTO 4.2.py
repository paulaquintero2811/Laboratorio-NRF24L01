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
spi = SPI(0, baudrate=1000000, polarity=0, phase=0,
          sck=Pin(18), mosi=Pin(19), miso=Pin(16))
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
FIFO_STATUS = 0x17

W_REGISTER = 0x20
R_RX_PAYLOAD = 0x61
W_TX_PAYLOAD = 0xA0
FLUSH_TX = 0xE1
FLUSH_RX = 0xE2
NOP = 0xFF

# =========================================================
# CONFIGURACION DEL SISTEMA
# =========================================================
# Canales disponibles: 70 a 80 (frecuencia = 2400 + canal MHz).
# Al llegar al 80 el siguiente valor vuelve al 70.
canales = list(range(70, 81))
canal_index = canales.index(76)      # canal inicial = 76

velocidades = ["250K", "1 Mbps", "2 Mbps"]
vel_corta = ["250K", "1M", "2M"]
velocidad_index = 1

potencias = ["-18 dBm", "-12 dBm", "-6 dBm", "0 dBm"]
pot_corta = ["-18", "-12", "-6", "0"]
potencia_index = 3

# El payload es de 32 bytes: 30 de mensaje + 2 de numero de secuencia
mensajes = [
    "EDIEM VALERO",
    "PAULA QUINTERO",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123",
]
mensaje_index = 0

modos = ["TX", "RX"]
modo_index = 0

envios = ["UNICO", "LOOP"]
envio_index = 1

# ACK automatico: OFF = medicion de alcance/BER, ON = TX sabe si RX recibio
acks = ["OFF", "ON"]
ack_index = 0

PERIODO_TX_MS = 10        # tiempo entre paquetes en modo LOOP
VERBOSO = False          # True = imprime cada paquete enviado/recibido

# Parametros del menu:
# 0 Canal, 1 Velocidad, 2 Potencia, 3 Mensaje, 4 Modo, 5 Envio, 6 ACK, 7 Enviar uno
N_PARAMETROS = 8
parametro = 0

# =========================================================
# CONTADORES
# =========================================================
secuencia = 0

# TX
enviados = 0
tx_ok = 0        # TX_DS: paquete salio (o fue confirmado si ACK=ON)
tx_fail = 0      # MAX_RT o timeout

# RX
recibidos = 0
corruptos = 0
perdidos = 0
ultima_seq = None
ultimo_texto = ""
t_ultimo_rx = 0

nrf_ok = False


def reset_contadores():
    global secuencia, enviados, tx_ok, tx_fail
    global recibidos, corruptos, perdidos, ultima_seq, ultimo_texto, t_ultimo_rx
    secuencia = 0
    enviados = 0
    tx_ok = 0
    tx_fail = 0
    recibidos = 0
    corruptos = 0
    perdidos = 0
    ultima_seq = None
    ultimo_texto = ""
    t_ultimo_rx = 0


# =========================================================
# FUNCIONES SPI NRF24L01
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
    """Envia un comando y devuelve el registro STATUS."""
    CSN.value(0)
    st = bytearray(1)
    spi.write_readinto(bytes([com]), st)
    CSN.value(1)
    return st[0]


# =========================================================
# CONFIGURACION DEL NRF24L01
# =========================================================
def configurar_rf_setup():
    if velocidad_index == 0:
        vel_bits = 0x20      # 250 kbps
    elif velocidad_index == 1:
        vel_bits = 0x00      # 1 Mbps
    else:
        vel_bits = 0x08      # 2 Mbps

    pot_bits = [0x00, 0x02, 0x04, 0x06][potencia_index]
    escribir_registro(RF_SETUP, vel_bits | pot_bits)


def configurar_nrf():
    global nrf_ok

    CE.value(0)
    escribir_registro(CONFIG, 0x00)
    time.sleep_ms(2)

    ack = (ack_index == 1)
    escribir_registro(EN_AA, 0x01 if ack else 0x00)
    # ARD = 500 us (necesario para 250 kbps), ARC = 1 reintento
    escribir_registro(SETUP_RETR, 0x11 if ack else 0x00)
    escribir_registro(EN_RXADDR, 0x01)
    escribir_registro(SETUP_AW, 0x03)
    escribir_registro(RF_CH, canales[canal_index])
    configurar_rf_setup()
    escribir_registro(RX_PW_P0, 32)

    direccion = b"RADIO"
    escribir_bytes(TX_ADDR, direccion)
    escribir_bytes(RX_ADDR_P0, direccion)

    comando(FLUSH_TX)
    comando(FLUSH_RX)
    escribir_registro(STATUS, 0x70)

    # CRC de 1 byte solo si ACK=ON (el ACK automatico lo exige)
    crc = 0x08 if ack else 0x00
    if modos[modo_index] == "TX":
        escribir_registro(CONFIG, crc | 0x02)   # PWR_UP, PRIM_RX=0
    else:
        escribir_registro(CONFIG, crc | 0x03)   # PWR_UP, PRIM_RX=1

    time.sleep_ms(5)

    if modos[modo_index] == "RX":
        CE.value(1)          # RX escucha de forma continua

    # Verificacion: si el modulo responde, SETUP_AW debe valer 3
    nrf_ok = (leer_registro(SETUP_AW) == 0x03)

    reset_contadores()


# =========================================================
# TRANSMITIR
# =========================================================
def transmitir(mensaje):
    """Envia un paquete de 32 bytes y espera TX_DS / MAX_RT.
    Devuelve True si el paquete salio bien."""
    global secuencia, enviados, tx_ok, tx_fail

    datos = mensaje.encode()[:30]
    datos = datos + bytes(30 - len(datos))
    datos = datos + bytes([(secuencia >> 8) & 0xFF, secuencia & 0xFF])
    secuencia = (secuencia + 1) & 0xFFFF

    comando(FLUSH_TX)
    CSN.value(0)
    spi.write(bytes([W_TX_PAYLOAD]))
    spi.write(datos)
    CSN.value(1)

    CE.value(1)
    time.sleep_us(20)
    CE.value(0)

    enviados += 1

    # Esperar resultado (max 20 ms)
    t0 = time.ticks_ms()
    st = 0
    while time.ticks_diff(time.ticks_ms(), t0) < 20:
        st = comando(NOP)
        if st & 0x30:
            break

    escribir_registro(STATUS, 0x30)   # limpiar TX_DS y MAX_RT

    if st & 0x20:
        tx_ok += 1
        if VERBOSO:
            print("[TX] paquete", secuencia - 1, "enviado OK")
        return True

    tx_fail += 1
    if VERBOSO:
        print("[TX] paquete", secuencia - 1, "FALLO")
    if st & 0x10:
        comando(FLUSH_TX)             # MAX_RT deja el paquete en el FIFO
    return False


# =========================================================
# RECIBIR
# =========================================================
def leer_payload():
    CSN.value(0)
    spi.write(bytes([R_RX_PAYLOAD]))
    d = spi.read(32)
    CSN.value(1)
    return d


def texto_visible(datos):
    return "".join(chr(b) if 32 <= b < 127 else "." for b in datos)


def procesar_rx():
    """Lee todos los paquetes del FIFO. Devuelve cuantos leyo."""
    global recibidos, corruptos, perdidos, ultima_seq
    global ultimo_texto, t_ultimo_rx

    leidos = 0
    st = comando(NOP)
    if not (st & 0x40):                      # RX_DR
        return 0

    while not (leer_registro(FIFO_STATUS) & 0x01):   # FIFO RX no vacio
        p = leer_payload()
        leidos += 1

        esperado = mensajes[mensaje_index].encode()[:30]
        esperado = esperado + bytes(30 - len(esperado))
        seq = (p[30] << 8) | p[31]

        recibidos += 1
        if bytes(p[:30]) != esperado:
            corruptos += 1

        if ultima_seq is not None:
            salto = (seq - ultima_seq - 1) & 0xFFFF
            if salto < 1000:                 # salto grande = TX reinicio / duplicado
                perdidos += salto
        ultima_seq = seq

        ultimo_texto = texto_visible(p[:30])
        t_ultimo_rx = time.ticks_ms()
        if VERBOSO:
            print("[RX] paquete", seq, "recibido:", ultimo_texto)

    escribir_registro(STATUS, 0x40)          # limpiar RX_DR
    return leidos


# =========================================================
# PANTALLAS
# =========================================================
def mostrar_inicio():
    oled.fill(0)
    oled.text("SISTEMA NRF24L01", 0, 0)
    oled.text("Comunicaciones", 0, 14)
    oled.text("Digitales UMNG", 0, 24)
    oled.text("Iniciando...", 0, 48)
    oled.show()
    time.sleep_ms(1500)

    oled.fill(0)
    oled.text("Canal: " + str(canales[canal_index]), 0, 0)
    oled.text("Freq: " + str(2400 + canales[canal_index]) + "MHz", 0, 12)
    oled.text("Vel: " + velocidades[velocidad_index], 0, 24)
    oled.text("Pot: " + potencias[potencia_index], 0, 36)
    oled.text("Modo: " + modos[modo_index], 0, 48)
    oled.show()
    time.sleep_ms(2000)


def mostrar_principal():
    oled.fill(0)
    oled.text("NRF24L01 OK" if nrf_ok else "NRF24L01 ERROR", 0, 0)
    oled.text("Canal: " + str(canales[canal_index]), 0, 12)
    oled.text("Vel: " + velocidades[velocidad_index], 0, 22)
    oled.text("Pot: " + potencias[potencia_index], 0, 32)
    oled.text("Modo: " + modos[modo_index], 0, 42)
    oled.text("Env: " + envios[envio_index], 0, 52)
    oled.show()


def mostrar_parametro():
    oled.fill(0)
    oled.text("PARAMETRO " + str(parametro + 1) + "/" + str(N_PARAMETROS), 0, 0)

    if parametro == 0:
        oled.text("CANAL", 0, 20)
        oled.text(str(canales[canal_index]) + " (" + str(2400 + canales[canal_index]) + ")", 0, 40)
    elif parametro == 1:
        oled.text("VELOCIDAD", 0, 20)
        oled.text(velocidades[velocidad_index], 0, 40)
    elif parametro == 2:
        oled.text("POTENCIA", 0, 20)
        oled.text(potencias[potencia_index], 0, 40)
    elif parametro == 3:
        m = mensajes[mensaje_index]
        oled.text("MENSAJE " + str(mensaje_index + 1) + "/" + str(len(mensajes)), 0, 20)
        oled.text(m[:16], 0, 36)
        if len(m) > 16:
            oled.text(m[16:32], 0, 46)
    elif parametro == 4:
        oled.text("MODO", 0, 20)
        oled.text(modos[modo_index], 0, 40)
    elif parametro == 5:
        oled.text("TIPO DE ENVIO", 0, 20)
        oled.text(envios[envio_index], 0, 40)
    elif parametro == 6:
        oled.text("ACK AUTOMATICO", 0, 20)
        oled.text(acks[ack_index], 0, 40)
    elif parametro == 7:
        oled.text("ENVIAR PAQUETE", 0, 20)
        oled.text("(solo en TX)", 0, 40)
    oled.show()


# =========================================================
# CAMBIAR VALORES
# =========================================================
def imprimir_config():
    print()
    print("Canal:", canales[canal_index], "->", 2400 + canales[canal_index], "MHz")
    print("Velocidad:", velocidades[velocidad_index])
    print("Potencia:", potencias[potencia_index])
    print("Modo:", modos[modo_index], "| Envio:", envios[envio_index], "| ACK:", acks[ack_index])
    print("Mensaje:", mensajes[mensaje_index])
    print("NRF responde:", nrf_ok)
    print("RF_CH =", leer_registro(RF_CH), " RF_SETUP =", hex(leer_registro(RF_SETUP)),
          " CONFIG =", hex(leer_registro(CONFIG)))


def cambiar_valor():
    global canal_index, velocidad_index, potencia_index
    global mensaje_index, modo_index, envio_index, ack_index
    global led_hasta

    if parametro == 7:
        if modos[modo_index] == "TX":
            ok = transmitir(mensajes[mensaje_index])
            led_hasta = time.ticks_add(time.ticks_ms(), 200)
            print("[TX] Paquete unico enviado:", "OK" if ok else "FALLO",
                  "| mensaje:", mensajes[mensaje_index])
        else:
            print("[INFO] Estas en modo RX, no se puede enviar")
        return

    if parametro == 0:
        canal_index = (canal_index + 1) % len(canales)
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
    elif parametro == 6:
        ack_index = (ack_index + 1) % len(acks)

    configurar_nrf()      # reinicia el modulo y los contadores
    imprimir_config()


# =========================================================
# INICIO
# =========================================================
print()
print("================================")
print("       SISTEMA NRF24L01")
print("================================")

led_hasta = 0
configurar_nrf()
imprimir_config()
mostrar_inicio()
mostrar_principal()

ultimo_b1 = 1
ultimo_b2 = 1
t_b1 = 0
t_b2 = 0
t_tx = 0
t_led = 0
t_print = 0
prev_enviados = 0
prev_recibidos = 0

# =========================================================
# LOOP PRINCIPAL
# =========================================================
while True:
    ahora = time.ticks_ms()

    # ---------- BOTONES (con antirrebote) ----------
    b1 = boton_parametro.value()
    b2 = boton_valor.value()

    if b1 == 0 and ultimo_b1 == 1 and time.ticks_diff(ahora, t_b1) > 150:
        parametro = (parametro + 1) % N_PARAMETROS
        t_b1 = ahora
        print("Parametro seleccionado:", parametro + 1)
        mostrar_parametro()

    if b2 == 0 and ultimo_b2 == 1 and time.ticks_diff(ahora, t_b2) > 150:
        cambiar_valor()
        t_b2 = ahora
        mostrar_parametro()

    ultimo_b1 = b1
    ultimo_b2 = b2

    # ---------- MODO TX ----------
    if modos[modo_index] == "TX":
        if nrf_ok and envios[envio_index] == "LOOP":
            if time.ticks_diff(ahora, t_tx) >= PERIODO_TX_MS:
                transmitir(mensajes[mensaje_index])
                t_tx = ahora
            if time.ticks_diff(ahora, t_led) >= 100:
                led.value(not led.value())
                t_led = ahora
        else:
            led.value(1 if time.ticks_diff(led_hasta, ahora) > 0 else 0)

    # ---------- MODO RX ----------
    else:
        if nrf_ok:
            procesar_rx()
            if recibidos > 0 and time.ticks_diff(ahora, t_ultimo_rx) < 150:
                led.value(1)
            else:
                led.value(0)

    # ---------- REPORTE EN CONSOLA (1 vez por segundo) ----------
    if time.ticks_diff(ahora, t_print) >= 1000:
        t_print = ahora

        if not nrf_ok:
            print("[ERROR] El NRF24L01 no responde, revisar cables")

        elif modos[modo_index] == "TX":
            if enviados != prev_enviados:
                print("[TX] ENVIANDO | enviados:", enviados,
                      "| OK:", tx_ok, "| fallos:", tx_fail,
                      "| mensaje:", mensajes[mensaje_index])
            else:
                print("[TX] No esta enviando (modo UNICO: usa 'Enviar un paquete')")
            prev_enviados = enviados

        else:
            if recibidos != prev_recibidos:
                total = recibidos + perdidos
                prr = (100 * recibidos / total) if total > 0 else 0
                print("[RX] RECIBIENDO | recibidos:", recibidos,
                      "| corruptos:", corruptos, "| perdidos:", perdidos,
                      "| PRR: %.1f%%" % prr, "| texto:", ultimo_texto)
            else:
                print("[RX] SIN SENAL (no llegan paquetes)")
            prev_recibidos = recibidos