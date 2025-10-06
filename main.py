from machine import I2C, Pin
import time
import network
import espnow

def u16(lo, hi):
    return (hi << 8) | lo

def s16(lo, hi):
    v = (hi << 8) | lo
    return v - 65536 if v & 0x8000 else v

def read_cal(i2c, addr):
    cal_reg = 0x88
    length = 24
    d = bytearray(length)
    i2c.readfrom_mem_into(addr, cal_reg, d)
    dig_T1 = u16(d[0], d[1])
    dig_T2 = s16(d[2], d[3])
    dig_T3 = s16(d[4], d[5])
    dig_P1 = u16(d[6], d[7])
    dig_P2 = s16(d[8], d[9])
    dig_P3 = s16(d[10], d[11])
    dig_P4 = s16(d[12], d[13])
    dig_P5 = s16(d[14], d[15])
    dig_P6 = s16(d[16], d[17])
    dig_P7 = s16(d[18], d[19])
    dig_P8 = s16(d[20], d[21])
    dig_P9 = s16(d[22], d[23])
    return {
        'T1': dig_T1,
        'T2': dig_T2,
        'T3': dig_T3,
        'P1': dig_P1,
        'P2': dig_P2,
        'P3': dig_P3,
        'P4': dig_P4,
        'P5': dig_P5,
        'P6': dig_P6,
        'P7': dig_P7,
        'P8': dig_P8,
        'P9': dig_P9
    }

def write_config(i2c, addr):
    try:
        i2c.writeto_mem(addr, 0xF2, bytes([0x01]))
        i2c.writeto_mem(addr, 0xF4, bytes([0x27]))
        i2c.writeto_mem(addr, 0xF5, bytes([0xA0]))
    except Exception:
        pass

def read_raw_bmp(i2c, addr):
    status = i2c.readfrom_mem(addr, 0xF3, 1)[0]
    if status & 0x08:
        time.sleep(0.01)
    d = i2c.readfrom_mem(addr, 0xF7, 6)
    pres = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
    temp = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
    return temp, pres

def compensate(cal, raw_t, raw_p):
    var1 = (raw_t / 16384.0 - cal['T1'] / 1024.0) * cal['T2']
    var2 = ((raw_t / 131072.0 - cal['T1'] / 8192.0) ** 2) * cal['T3']
    t_fine = var1 + var2
    temp = t_fine / 5120.0
    var1 = t_fine / 2.0 - 64000.0
    var2 = var1 * var1 * cal.get('P6', 0) / 32768.0
    var2 = var2 + var1 * cal.get('P5', 0) * 2.0
    var2 = var2 / 4.0 + cal.get('P4', 0) * 65536.0
    var1 = (cal.get('P3', 0) * var1 * var1 / 524288.0 + cal.get('P2', 0) * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * cal.get('P1', 1)
    pressure = 1048576.0 - raw_p
    if var1 != 0:
        pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
        var1 = cal.get('P9', 0) * pressure * pressure / 2147483648.0
        var2 = pressure * cal.get('P8', 0) / 32768.0
        pressure = pressure + (var1 + var2 + cal.get('P7', 0)) / 16.0
    else:
        pressure = 0
    return temp, pressure

def find_bmp(i2c):
    addresses = (0x76, 0x77)
    for a in addresses:
        try:
            cid = bytearray(1)
            i2c.readfrom_mem_into(a, 0xD0, cid)
            if cid[0] in (0x58, 0x60):
                return a, cid[0]
        except Exception:
            pass
    return None, None

def init_espnow(receiver_mac, channel):
    import network, espnow
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(channel=channel)
    wlan.disconnect()
    e = espnow.ESPNow()
    e.active(True)
    try:
        if receiver_mac != b'\xff\xff\xff\xff\xff\xff':
            e.add_peer(receiver_mac, channel=channel, encrypt=False)
    except Exception:
        pass
    return e

def send_temperature(e, receiver_mac, temp_str):
    if not e or not receiver_mac or not isinstance(receiver_mac, bytes) or len(receiver_mac) != 6:
        return False
    try:
        e.send(receiver_mac, temp_str)
        return True
    except Exception:
        try:
            e.send(receiver_mac, temp_str)
            return True
        except Exception:
            return False

def main():
    sda_pin = 3
    scl_pin = 5
    i2c_freq = 100000
    i2c = I2C(0, scl=Pin(scl_pin), sda=Pin(sda_pin), freq=i2c_freq)
    bmp_addr, bmp_cid = find_bmp(i2c)
    aht_addr = 0x38
    if not bmp_addr:
        print("No BMP found at 0x76/0x77")
        return
    cal = read_cal(i2c, bmp_addr)
    write_config(i2c, bmp_addr)
    receiver_mac = bytes.fromhex('0c4ea0631a1c')
    channel = 1
    e = init_espnow(receiver_mac, channel)
    seq = 0
    while True:
        try:
            raw_t, raw_p = read_raw_bmp(i2c, bmp_addr)
            print("Raw temp:", raw_t, "Raw press:", raw_p)
            temp, press = compensate(cal, raw_t, raw_p)
            temp_str = ("{:.2f}".format(temp)).encode()
            sent = send_temperature(e, receiver_mac, temp_str)
            print("Temp:", temp_str.decode(), "Sent" if sent else "Not sent", seq)
            seq = seq + 1
        except Exception as exc:
            print("Read error", exc)
        time.sleep(1)

if __name__ == "__main__":
    main()

