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
# COMANDOS
# =========================

W_TX_PAYLOAD = 0xA0
FLUSH_TX = 0xE1


# =========================
# ENVIAR PAYLOAD AL NRF
# =========================

def cargar_paquete(mensaje):

    # Convertir mensaje a bytes
    datos = mensaje.encode()

    # Completar hasta 32 bytes
    datos = datos + bytes(32 - len(datos))


    # Limpiar FIFO de transmisión
    CSN.value(0)

    spi.write(
        bytes([FLUSH_TX])
    )

    CSN.value(1)


    # Cargar nuevo paquete
    CSN.value(0)

    # Comando W_TX_PAYLOAD
    spi.write(
        bytes([W_TX_PAYLOAD])
    )

    # Datos del mensaje
    spi.write(datos)

    CSN.value(1)


# =========================
# PRUEBA
# =========================

print("PRUEBA 3: TRANSFERENCIA DE PAQUETE")
print("Mensaje: EDIEM VALERO")
print("Comando: 0xA0")
print()

while True:

    cargar_paquete(
        "EDIEM VALERO"
    )

    print(
        "Paquete cargado: EDIEM VALERO"
    )

    time.sleep_ms(500)