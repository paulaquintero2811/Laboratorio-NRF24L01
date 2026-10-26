
from machine import Pin, SPI, I2C
import time
import gc
import ssd1306

# =========================================================
# NRF24L01 + OLED + BOTONES + TRANSFERENCIA DE ARCHIVOS
# Instalar el mismo main.py en ambas Raspberry Pi Pico.
# =========================================================

# OLED
i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400000)
oled = ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)

# Botones y LED
boton_parametro = Pin(10, Pin.IN, Pin.PULL_UP)
boton_valor = Pin(11, Pin.IN, Pin.PULL_UP)
led = Pin(12, Pin.OUT)
led.value(0)

# SPI NRF24L01
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
FIFO_STATUS = 0x17

W_REGISTER = 0x20
R_RX_PAYLOAD = 0x61
W_TX_PAYLOAD = 0xA0
FLUSH_TX = 0xE1
FLUSH_RX = 0xE2
NOP = 0xFF

# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

canales = list(range(70, 81))
canal_index = canales.index(71)

velocidades = ["250K", "1 Mbps", "2 Mbps"]
velocidad_index = 1

potencias = ["-18 dBm", "-12 dBm", "-6 dBm", "0 dBm"]
potencia_index = 3

modos = ["TX", "RX"]
modo_index = 0

envios = ["UNICO", "LOOP"]
envio_index = 1

acks = ["OFF", "ON"]
ack_index = 0

operaciones = ["MENSAJE", "ARCHIVO"]
operacion_index = 0

mensajes = [
    "EDIEM VALERO",
    "PAULA QUINTERO",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"
]
mensaje_index = 0

nombres_archivo = ["alfabeto.txt", "aleatorio.txt"]
etiquetas_archivo = ["ALFABETO", "ALEATORIO"]
archivo_index = 0

# =========================================================
# TRANSFERENCIA DE ARCHIVOS
# =========================================================

TAM_PAYLOAD = 32
TAM_DATOS = 28
PERIODO_TX_MS = 10

# 0 Canal
# 1 Velocidad
# 2 Potencia
# 3 Mensaje
# 4 Modo TX/RX
# 5 Tipo de envío
# 6 ACK
# 7 Operación mensaje/archivo
# 8 Archivo
# 9 Iniciar envío

N_PARAMETROS = 10
parametro = 0

PKT_MENSAJE = 0x10
PKT_INICIO = 0xF0
PKT_DATOS = 0xD1
PKT_FIN = 0xF1

nrf_ok = False
archivo_local = b""
archivo_local_ok = False

tx_activo = False
tx_indice = 0
tx_mensaje_una_vez = False

rx_archivo_abierto = False
rx_archivo = None
rx_nombre_salida = "recibido.txt"
rx_bytes = 0
rx_checksum = 0
rx_seq_esperada = 0
rx_paquetes_ok = 0
rx_paquetes_perdidos = 0
rx_bits_comparados = 0
rx_bits_errados = 0
rx_t_ultimo = 0

# =========================================================
# FUNCIONES SPI
# =========================================================

def escribir_registro(reg, valor):
    CSN.value(0)
    spi.write(bytes([W_REGISTER | reg, valor]))
    CSN.value(1)


def leer_registro(reg):
    CSN.value(0)
    spi.write(bytes([reg]))
    valor = spi.read(1, 0x00)[0]
    CSN.value(1)
    return valor


def escribir_bytes(reg, datos):
    CSN.value(0)
    spi.write(bytes([W_REGISTER | reg]))
    spi.write(bytes(datos))
    CSN.value(1)


def comando(cmd):
    CSN.value(0)
    st = bytearray(1)
    spi.write_readinto(bytes([cmd]), st)
    CSN.value(1)
    return st[0]


# =========================================================
# CONFIGURAR VELOCIDAD Y POTENCIA
# =========================================================

def configurar_rf_setup():
    vel_bits = [0x20, 0x00, 0x08][velocidad_index]
    pot_bits = [0x00, 0x02, 0x04, 0x06][potencia_index]
    escribir_registro(RF_SETUP, vel_bits | pot_bits)


# =========================================================
# CONFIGURAR NRF24L01
# =========================================================

def configurar_nrf():
    global nrf_ok

    CE.value(0)
    escribir_registro(CONFIG, 0x00)
    time.sleep_ms(2)

    ack = ack_index == 1

    escribir_registro(EN_AA, 0x01 if ack else 0x00)
    escribir_registro(SETUP_RETR, 0x15 if ack else 0x00)
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

    # CRC habilitado cuando ACK está activado.
    crc = 0x08 if ack else 0x00

    if modos[modo_index] == "TX":
        escribir_registro(CONFIG, crc | 0x02)
    else:
        escribir_registro(CONFIG, crc | 0x03)

    time.sleep_ms(5)

    if modos[modo_index] == "RX":
        CE.value(1)

    nrf_ok = leer_registro(SETUP_AW) == 0x03


# =========================================================
# ARCHIVO LOCAL
# =========================================================

def checksum16(datos):
    suma = 0
    for b in datos:
        suma = (suma + b) & 0xFFFF
    return suma


def cargar_archivo_local():
    global archivo_local, archivo_local_ok

    archivo_local = b""
    archivo_local_ok = False
    gc.collect()

    nombre = nombres_archivo[archivo_index]

    try:
        with open(nombre, "rb") as f:
            archivo_local = f.read()
    except OSError:
        print("[ERROR] No se encuentra", nombre, "en esta Pico.")
        return False

    if not archivo_local:
        print("[ERROR] El archivo está vacío:", nombre)
        return False

    archivo_local_ok = True

    print(
        "Archivo local:", nombre,
        "| bytes:", len(archivo_local),
        "| checksum16:", checksum16(archivo_local)
    )

    return True


# =========================================================
# CONSTRUIR PAQUETES DE 32 BYTES
# =========================================================

def preparar_payload(tipo, secuencia=0, longitud=0, datos=b""):
    datos = datos[:TAM_DATOS]

    encabezado = bytes([
        tipo,
        (secuencia >> 8) & 255,
        secuencia & 255,
        longitud & 255
    ])

    return encabezado + datos + bytes(TAM_DATOS - len(datos))


# =========================================================
# TRANSMITIR PAQUETE
# =========================================================

def enviar_payload(payload):
    if len(payload) != TAM_PAYLOAD:
        print("[TX ERROR] El paquete no tiene 32 bytes.")
        return False

    comando(FLUSH_TX)
    escribir_registro(STATUS, 0x30)

    CSN.value(0)
    spi.write(bytes([W_TX_PAYLOAD]))
    spi.write(payload)
    CSN.value(1)

    CE.value(1)
    time.sleep_us(15)
    CE.value(0)

    t0 = time.ticks_ms()
    estado = 0

    while time.ticks_diff(time.ticks_ms(), t0) < 15:
        estado = comando(NOP)

        if estado & 0x30:
            break

        time.sleep_us(100)

    escribir_registro(STATUS, 0x30)

    ok = bool(estado & 0x20)

    if not ok:
        comando(FLUSH_TX)

    return ok


# =========================================================
# ENVÍO DE MENSAJES
# =========================================================

def transmitir_mensaje(mensaje):
    datos = mensaje.encode("ascii")[:TAM_DATOS]

    payload = preparar_payload(
        PKT_MENSAJE,
        0,
        len(datos),
        datos
    )

    ok = enviar_payload(payload)

    if ok:
        print("[TX] Mensaje enviado:", mensaje)
    else:
        print("[TX] No se confirmó el envío.")

    return ok


# =========================================================
# INICIAR ENVÍO DE ARCHIVO
# =========================================================

def iniciar_transferencia_archivo():
    global tx_activo, tx_indice

    if not archivo_local_ok:
        if not cargar_archivo_local():
            return

    tam = len(archivo_local)
    nombre_id = archivo_index

    datos = bytes([
        (tam >> 24) & 255,
        (tam >> 16) & 255,
        (tam >> 8) & 255,
        tam & 255,
        nombre_id
    ])

    inicio = preparar_payload(
        PKT_INICIO,
        0,
        len(datos),
        datos
    )

    print(
        "[TX] Inicio de archivo:",
        nombres_archivo[archivo_index],
        "| bytes:", tam,
        "| checksum16:", checksum16(archivo_local)
    )

    enviar_payload(inicio)

    tx_indice = 0
    tx_activo = True


# =========================================================
# ENVIAR BLOQUES DEL ARCHIVO
# =========================================================

def transmitir_bloque_archivo():
    global tx_indice, tx_activo

    total_bloques = (
        len(archivo_local) + TAM_DATOS - 1
    ) // TAM_DATOS

    if tx_indice < total_bloques:
        inicio = tx_indice * TAM_DATOS

        bloque = archivo_local[
            inicio:inicio + TAM_DATOS
        ]

        payload = preparar_payload(
            PKT_DATOS,
            tx_indice,
            len(bloque),
            bloque
        )

        enviar_payload(payload)

        tx_indice += 1

        if tx_indice % 50 == 0 or tx_indice == total_bloques:
            print(
                "[TX] Archivo:",
                tx_indice, "/", total_bloques, "bloques"
            )

        return

    tam = len(archivo_local)
    suma = checksum16(archivo_local)

    datos = bytes([
        (tam >> 24) & 255,
        (tam >> 16) & 255,
        (tam >> 8) & 255,
        tam & 255,
        (suma >> 8) & 255,
        suma & 255
    ])

    fin = preparar_payload(
        PKT_FIN,
        total_bloques,
        len(datos),
        datos
    )

    enviar_payload(fin)

    tx_activo = False

    print(
        "[TX] Transferencia finalizada.",
        "Bloques:", total_bloques,
        "| tamaño:", tam,
        "| checksum16:", suma
    )


# =========================================================
# RECEPCIÓN DE PAQUETES
# =========================================================

def leer_payload():
    CSN.value(0)
    spi.write(bytes([R_RX_PAYLOAD]))
    datos = spi.read(32, 0x00)
    CSN.value(1)
    return datos


def cerrar_rx_archivo():
    global rx_archivo_abierto, rx_archivo

    if rx_archivo is not None:
        try:
            rx_archivo.close()
        except Exception:
            pass

    rx_archivo = None
    rx_archivo_abierto = False


# =========================================================
# PROCESAR PAQUETES RECIBIDOS
# =========================================================

def procesar_paquete_rx():
    global rx_archivo_abierto, rx_archivo
    global rx_nombre_salida
    global rx_bytes, rx_checksum, rx_seq_esperada
    global rx_paquetes_ok, rx_paquetes_perdidos
    global rx_bits_comparados, rx_bits_errados
    global rx_t_ultimo

    estado = comando(NOP)

    if not (estado & 0x40):
        return

    while not (leer_registro(FIFO_STATUS) & 0x01):
        p = leer_payload()

        rx_t_ultimo = time.ticks_ms()

        tipo = p[0]
        seq = (p[1] << 8) | p[2]
        longitud = p[3]

        if longitud > TAM_DATOS:
            continue

        datos = p[4:4 + longitud]

        # -----------------------------------------------
        # MENSAJE
        # -----------------------------------------------

        if tipo == PKT_MENSAJE:
            texto = "".join(
                chr(b) if 32 <= b <= 126 else "?"
                for b in datos
            )

            print("[RX] Mensaje:", texto)

        # -----------------------------------------------
        # INICIO DE ARCHIVO
        # -----------------------------------------------

        elif tipo == PKT_INICIO:
            if len(datos) < 5:
                continue

            cerrar_rx_archivo()

            tam = (
                (datos[0] << 24)
                | (datos[1] << 16)
                | (datos[2] << 8)
                | datos[3]
            )

            archivo_id = datos[4]

            if archivo_id == 0:
                rx_nombre_salida = "recibido_alfabeto.txt"
            else:
                rx_nombre_salida = "recibido_aleatorio.txt"

            try:
                rx_archivo = open(rx_nombre_salida, "wb")
                rx_archivo_abierto = True

                rx_bytes = 0
                rx_checksum = 0
                rx_seq_esperada = 0
                rx_paquetes_ok = 0
                rx_paquetes_perdidos = 0
                rx_bits_comparados = 0
                rx_bits_errados = 0

                print(
                    "[RX] Transferencia iniciada.",
                    "Guardando en:", rx_nombre_salida,
                    "| bytes esperados:", tam
                )

            except OSError as e:
                rx_archivo = None
                rx_archivo_abierto = False
                print("[RX ERROR] No se pudo crear el archivo:", e)

        # -----------------------------------------------
        # BLOQUES DE DATOS
        # -----------------------------------------------

        elif tipo == PKT_DATOS:
            if not rx_archivo_abierto or rx_archivo is None:
                continue

            # Ignorar duplicados
            if seq < rx_seq_esperada:
                continue

            # Registrar los bloques perdidos
            if seq > rx_seq_esperada:
                faltantes = seq - rx_seq_esperada
                rx_paquetes_perdidos += faltantes

                # Insertar ceros como marcadores de pérdida
                rx_archivo.write(bytes(faltantes * TAM_DATOS))
                rx_bytes += faltantes * TAM_DATOS

            rx_archivo.write(datos)
            rx_bytes += len(datos)

            for b in datos:
                rx_checksum = (rx_checksum + b) & 0xFFFF

            # Comparar contra el archivo de referencia local
            if archivo_local_ok:
                inicio_ref = seq * TAM_DATOS
                referencia = archivo_local[
                    inicio_ref:inicio_ref + len(datos)
                ]

                ncomp = min(len(referencia), len(datos))
                rx_bits_comparados += ncomp * 8

                for j in range(ncomp):
                    rx_bits_errados += bin(
                        datos[j] ^ referencia[j]
                    ).count("1")

            rx_seq_esperada = seq + 1
            rx_paquetes_ok += 1

            if rx_paquetes_ok % 50 == 0:
                print("[RX] Bloques guardados:", rx_paquetes_ok)

        # -----------------------------------------------
        # FIN DE ARCHIVO
        # -----------------------------------------------

        elif tipo == PKT_FIN:
            if not rx_archivo_abierto or rx_archivo is None:
                continue

            if len(datos) < 6:
                continue

            rx_archivo.flush()
            cerrar_rx_archivo()

            tam_tx = (
                (datos[0] << 24)
                | (datos[1] << 16)
                | (datos[2] << 8)
                | datos[3]
            )

            suma_tx = (datos[4] << 8) | datos[5]

            print()
            print("========== ARCHIVO RECIBIDO ==========")
            print("Archivo guardado:", rx_nombre_salida)
            print("Bytes guardados:", rx_bytes)
            print("Bytes esperados:", tam_tx)
            print("Bloques recibidos:", rx_paquetes_ok)
            print("Bloques perdidos:", rx_paquetes_perdidos)
            print("Checksum RX:", rx_checksum)
            print("Checksum TX:", suma_tx)
            print("Bits comparados:", rx_bits_comparados)
            print("Bits errados:", rx_bits_errados)

            if rx_bits_comparados > 0:
                ber = rx_bits_errados / rx_bits_comparados
                print("BER: %.6e" % ber)
            else:
                print("BER: no calculable.")

            if (
                rx_bytes == tam_tx
                and rx_checksum == suma_tx
                and rx_paquetes_perdidos == 0
            ):
                print("Integridad: CORRECTA")
            else:
                print("Integridad: REVISAR; hubo pérdida o corrupción.")

            print("======================================")
            print("Archivo guardado en la memoria de la Pico RX.")
            print()

    escribir_registro(STATUS, 0x40)


# =========================================================
# PANTALLA PRINCIPAL
# =========================================================

def mostrar_principal():
    oled.fill(0)

    oled.text(
        "NRF24L01 " + ("OK" if nrf_ok else "ERROR"),
        0, 0
    )

    oled.text(
        "CH:" + str(canales[canal_index])
        + " " + str(2400 + canales[canal_index]),
        0, 12
    )

    oled.text("Vel:" + velocidades[velocidad_index], 0, 22)
    oled.text("Pot:" + potencias[potencia_index], 0, 32)
    oled.text("Modo:" + modos[modo_index], 0, 42)

    if operacion_index == 0:
        oled.text("MSG:" + mensajes[mensaje_index][:12], 0, 52)
    else:
        oled.text("FILE:" + etiquetas_archivo[archivo_index], 0, 52)

    oled.show()


# =========================================================
# PANTALLA DEL MENÚ
# =========================================================

def mostrar_parametro():
    oled.fill(0)

    oled.text(
        "MENU " + str(parametro + 1) + "/" + str(N_PARAMETROS),
        0, 0
    )

    opciones = [
        ("CANAL", str(canales[canal_index])),
        ("VELOCIDAD", velocidades[velocidad_index]),
        ("POTENCIA", potencias[potencia_index]),
        ("MENSAJE", mensajes[mensaje_index][:16]),
        ("MODO", modos[modo_index]),
        ("ENVIO", envios[envio_index]),
        ("ACK", acks[ack_index]),
        ("OPERACION", operaciones[operacion_index]),
        ("ARCHIVO", etiquetas_archivo[archivo_index]),
        (
            "INICIAR",
            "Enviar archivo"
            if operacion_index == 1
            else "Enviar mensaje"
        )
    ]

    oled.text(opciones[parametro][0], 0, 22)
    oled.text(opciones[parametro][1], 0, 42)
    oled.show()


# =========================================================
# MOSTRAR CONFIGURACIÓN EN CONSOLA
# =========================================================

def imprimir_config():
    print()
    print(
        "Canal:", canales[canal_index],
        "| Frecuencia:", 2400 + canales[canal_index], "MHz"
    )
    print(
        "Velocidad:", velocidades[velocidad_index],
        "| Potencia:", potencias[potencia_index]
    )
    print(
        "Modo:", modos[modo_index],
        "| Operación:", operaciones[operacion_index]
    )
    print("ACK:", acks[ack_index], "| NRF responde:", nrf_ok)
    print("Dirección común: RADIO")

    if operacion_index == 1:
        print(
            "Archivo:", nombres_archivo[archivo_index],
            "| disponible:", archivo_local_ok
        )


# =========================================================
# CAMBIAR VALORES CON EL BOTÓN
# =========================================================

def cambiar_valor():
    global canal_index, velocidad_index, potencia_index
    global mensaje_index, modo_index, envio_index, ack_index
    global operacion_index, archivo_index
    global tx_activo, tx_mensaje_una_vez

    if parametro == 9:
        if modos[modo_index] == "RX":
            print("[RX] Listo para recibir.")
            print("[RX] El archivo se guardará automáticamente.")
            return

        if operacion_index == 0:
            if envios[envio_index] == "UNICO":
                transmitir_mensaje(mensajes[mensaje_index])
            else:
                tx_mensaje_una_vez = False
                print("[TX] Modo LOOP: enviando mensajes.")

        else:
            if cargar_archivo_local():
                iniciar_transferencia_archivo()

        return

    if parametro == 0:
        canal_index = (canal_index + 1) % len(canales)

    elif parametro == 1:
        velocidad_index = (
            velocidad_index + 1
        ) % len(velocidades)

    elif parametro == 2:
        potencia_index = (
            potencia_index + 1
        ) % len(potencias)

    elif parametro == 3:
        mensaje_index = (
            mensaje_index + 1
        ) % len(mensajes)

    elif parametro == 4:
        modo_index = (modo_index + 1) % len(modos)

    elif parametro == 5:
        envio_index = (envio_index + 1) % len(envios)

    elif parametro == 6:
        ack_index = (ack_index + 1) % len(acks)

    elif parametro == 7:
        operacion_index = (
            operacion_index + 1
        ) % len(operaciones)

    elif parametro == 8:
        archivo_index = (
            archivo_index + 1
        ) % len(nombres_archivo)

        cargar_archivo_local()

    configurar_nrf()
    imprimir_config()
    mostrar_principal()


# =========================================================
# INICIALIZACIÓN
# =========================================================

print()
print("========================================")
print(" NRF24L01 UMNG - MENSAJES Y ARCHIVOS")
print("========================================")

cargar_archivo_local()
configurar_nrf()
imprimir_config()
mostrar_principal()

ultimo_b1 = 1
ultimo_b2 = 1
t_b1 = 0
t_b2 = 0
t_tx = 0
t_led = 0
estado_led = 0

# =========================================================
# BUCLE PRINCIPAL
# =========================================================

while True:
    ahora = time.ticks_ms()

    b1 = boton_parametro.value()
    b2 = boton_valor.value()

    # Botón 1: seleccionar parámetro
    if (
        b1 == 0
        and ultimo_b1 == 1
        and time.ticks_diff(ahora, t_b1) > 150
    ):
        parametro = (parametro + 1) % N_PARAMETROS
        t_b1 = ahora
        mostrar_parametro()

    # Botón 2: cambiar valor o iniciar
    if (
        b2 == 0
        and ultimo_b2 == 1
        and time.ticks_diff(ahora, t_b2) > 150
    ):
        cambiar_valor()
        t_b2 = ahora
        mostrar_parametro()

    ultimo_b1 = b1
    ultimo_b2 = b2

    # -----------------------------------------------
    # TRANSMISOR
    # -----------------------------------------------

    if modos[modo_index] == "TX":

        if (
            operacion_index == 0
            and envios[envio_index] == "LOOP"
        ):
            if time.ticks_diff(ahora, t_tx) >= PERIODO_TX_MS:
                transmitir_mensaje(mensajes[mensaje_index])
                t_tx = ahora

        elif operacion_index == 1 and tx_activo:
            if time.ticks_diff(ahora, t_tx) >= PERIODO_TX_MS:
                transmitir_bloque_archivo()
                t_tx = ahora

        if time.ticks_diff(ahora, t_led) >= 100:
            estado_led = not estado_led
            led.value(estado_led)
            t_led = ahora

    # -----------------------------------------------
    # RECEPTOR
    # -----------------------------------------------

    else:
        procesar_paquete_rx()

        if (
            rx_t_ultimo
            and time.ticks_diff(ahora, rx_t_ultimo) < 150
        ):
            led.value(1)
        else:
            led.value(0)

    time.sleep_ms(1)
