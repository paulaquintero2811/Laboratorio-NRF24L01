from machine import Pin, SPI
import time

# SPI
spi = SPI(
    0,
    baudrate=1000000,
    polarity=0,
    phase=0,
    sck=Pin(18),
    mosi=Pin(19),
    miso=Pin(16)
)

# NRF24L01
CE = Pin(17, Pin.OUT)
CSN = Pin(20, Pin.OUT)

CE.value(0)
CSN.value(1)


def leer_registro(reg):

    CSN.value(0)

    # Solicitar lectura del registro
    spi.write(bytes([reg]))

    # Recibir el dato del registro
    respuesta = spi.read(1)

    CSN.value(1)

    return respuesta[0]


print("Iniciando lectura de RF_CH...")

while True:

    valor = leer_registro(0x05)

    print(
        "RF_CH =",
        valor,
        "HEX =",
        hex(valor)
    )

    time.sleep_ms(500)