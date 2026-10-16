from machine import Pin, SPI
import time

# =========================
# SPI
# =========================

spi = SPI(
    0,
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=Pin(18),
    mosi=Pin(19),
    miso=Pin(16)
)

# =========================
# NRF24L01
# =========================

CE = Pin(17, Pin.OUT)
CSN = Pin(20, Pin.OUT)

CE.value(0)
CSN.value(1)


# =========================
# ESCRIBIR REGISTRO
# =========================

def escribir_registro(registro, valor):

    CSN.value(0)

    # Comando de escritura
    spi.write(
        bytes([0x20 | registro])
    )

    # Valor que queremos escribir
    spi.write(
        bytes([valor])
    )

    CSN.value(1)


# =========================
# LEER REGISTRO
# =========================

def leer_registro(registro):

    CSN.value(0)

    spi.write(
        bytes([registro])
    )

    respuesta = spi.read(1)

    CSN.value(1)

    return respuesta[0]


# =========================
# PRUEBA
# =========================

print("Iniciando prueba de escritura...")

time.sleep_ms(500)

# Escribir RF_CH = 76
escribir_registro(0x05, 76)

print("RF_CH escrito = 76")

time.sleep_ms(100)

# Leer para comprobar
valor = leer_registro(0x05)

print(
    "RF_CH leido =",
    valor,
    "HEX =",
    hex(valor)
)

print("Prueba terminada")