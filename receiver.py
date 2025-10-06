from machine import Pin, I2C
import framebuf
from micropython import const
import network
import espnow
import time

SET_CONTRAST = const(0x81)
SET_ENTIRE_ON = const(0xA4)
SET_NORM_INV = const(0xA6)
SET_DISP = const(0xAE)
SET_MEM_ADDR = const(0x20)
SET_COL_ADDR = const(0x21)
SET_PAGE_ADDR = const(0x22)
SET_DISP_START_LINE = const(0x40)
SET_SEG_REMAP = const(0xA0)
SET_MUX_RATIO = const(0xA8)
SET_COM_OUT_DIR = const(0xC0)
SET_DISP_OFFSET = const(0xD3)
SET_COM_PIN_CFG = const(0xDA)
SET_DISP_CLK_DIV = const(0xD5)
SET_PRECHARGE = const(0xD9)
SET_VCOM_DESEL = const(0xDB)
SET_CHARGE_PUMP = const(0x8D)

class SSD1306:
    def __init__(self, width, height, external_vcc):
        self.width = width
        self.height = height
        self.external_vcc = external_vcc
        self.pages = self.height // 8
        self.buffer = bytearray(((height // 8) * width) + 1)
        self.buffer[0] = 0x40
        self.framebuf = framebuf.FrameBuffer1(memoryview(self.buffer)[1:], width, height)

    def write_cmd(self, cmd):
        self.temp[0] = 0x80
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def poweroff(self):
        self.write_cmd(SET_DISP | 0x00)

    def poweron(self):
        self.write_cmd(SET_DISP | 0x01)

    def contrast(self, contrast):
        self.write_cmd(SET_CONTRAST)
        self.write_cmd(contrast)

    def invert(self, invert):
        self.write_cmd(SET_NORM_INV | (invert & 1))

    def init_display(self):
        for cmd in (
            SET_DISP | 0x00,
            SET_MEM_ADDR,
            0x00,
            SET_DISP_START_LINE | 0x00,
            SET_SEG_REMAP | 0x01,
            SET_MUX_RATIO,
            self.height - 1,
            SET_COM_OUT_DIR | 0x08,
            SET_DISP_OFFSET,
            0x00,
            SET_COM_PIN_CFG,
            0x12,
            SET_DISP_CLK_DIV,
            0x80,
            SET_PRECHARGE,
            0xF1,
            SET_VCOM_DESEL,
            0x30,
            SET_CONTRAST,
            0xFF,
            SET_ENTIRE_ON,
            SET_NORM_INV,
            SET_CHARGE_PUMP,
            0x14,
            SET_DISP | 0x01,
        ):
            self.write_cmd(cmd)

    def fill(self, col):
        self.framebuf.fill(col)

    def pixel(self, x, y, col):
        self.framebuf.pixel(x, y, col)

    def scroll(self, dx, dy):
        self.framebuf.scroll(dx, dy)

    def text(self, string, x, y, col=1):
        self.framebuf.text(string, x, y, col)

    def show(self):
        self.buffer[0] = 0x40
        self.i2c.writeto(self.addr, self.buffer)

    def text_scaled(self, string, x, y, scale=None, max_scale=None, col=1, spacing=1):
        if scale is None:
            scale = 1
        if max_scale is not None and scale > max_scale:
            scale = max_scale
        if scale == 1:
            self.text(string, x, y, col)
            return
        for ch in string:
            buf = bytearray(8)
            fbch = framebuf.FrameBuffer(buf, 8, 8, framebuf.MONO_HLSB)
            fbch.fill(0)
            fbch.text(ch, 0, 0, 1)
            for cy in range(8):
                for cx in range(8):
                    if fbch.pixel(cx, cy):
                        bx = x + cx * scale
                        by = y + cy * scale
                        if by < 0 or by >= self.height:
                            continue
                        for sy in range(scale):
                            py = by + sy
                            if py < 0 or py >= self.height:
                                continue
                            row_base = bx
                            for sx in range(scale):
                                px = row_base + sx
                                if px < 0 or px >= self.width:
                                    continue
                                self.pixel(px, py, col)
            x += 8 * scale + spacing * scale

class SSD1306_I2C(SSD1306):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.i2c = i2c
        self.addr = addr
        self.temp = bytearray(2)
        super().__init__(width, height, external_vcc)
        self.poweron()
        self.init_display()
        self.fill(0)
        self.show()

def init_espnow(channel):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(channel=channel)
    wlan.disconnect()
    e = espnow.ESPNow()
    e.active(True)
    return e

def scan_i2c(i2c_dev):
    print('Scanning I2C...')
    devices = []
    for addr in range(128):
        try:
            i2c_dev.writeto(addr, b'\x00')
            devices.append(hex(addr))
        except OSError:
            pass
    print('Found devices:', devices)
    return devices

def main():
    SDA_PIN = 5
    SCL_PIN = 6
    I2C_ID = 0
    I2C_ADDR = 0x3C
    OFFSET_X = 28
    OFFSET_Y = 24
    C_HIDE_MS = 300
    DISPLAY_UPDATE_MS = 1000
    sda_pin = SDA_PIN
    scl_pin = SCL_PIN
    i2c = I2C(I2C_ID, sda=Pin(sda_pin), scl=Pin(scl_pin))
    scan_i2c(i2c)
    oled = SSD1306_I2C(128, 64, i2c, addr=I2C_ADDR)
    oled.contrast(255)
    channel = 1
    e = init_espnow(channel)
    last_update = time.ticks_ms()
    last_recv = time.ticks_ms() - 10000
    temp = 0.0
    while True:
        if e.any():
            mac, data = e.recv()
            if data:
                try:
                    temp_str = data.decode()
                    temp = float(temp_str)
                except Exception:
                    pass
                last_recv = time.ticks_ms()
        now = time.ticks_ms()
        if time.ticks_diff(now, last_update) > DISPLAY_UPDATE_MS:
            oled.fill(0)
            num_str = '{:.1f}'.format(temp)
            avail_w = oled.width - 2 * OFFSET_X
            avail_h = oled.height - 2 * OFFSET_Y
            if avail_w <= 0 or avail_h <= 0:
                x_pos = 0
                y_pos = 0
                scale = 1
            else:
                max_scale_by_height = avail_h // 8
                if max_scale_by_height < 1:
                    max_scale_by_height = 1
                max_scale_by_width = avail_w // (len(num_str) * 8) if len(num_str) > 0 else 1
                if max_scale_by_width < 1:
                    max_scale_by_width = 1
                scale = min(max_scale_by_height, max_scale_by_width)
                if scale < 1:
                    scale = 1
                unit_scale = max(1, scale - 1)
            hide_c = time.ticks_diff(now, last_recv) < C_HIDE_MS
            num_w = len(num_str) * 8 * scale
            unit_w = 0 if hide_c else 8 * unit_scale
            spacing = 1 * scale if unit_w else 0
            total_w = num_w + unit_w + spacing
            x_pos = OFFSET_X + max(0, (avail_w - total_w) // 2)
            y_pos = OFFSET_Y + max(0, (avail_h - 8 * scale) // 2)
            oled.text_scaled(num_str, x_pos, y_pos, scale=scale, col=1, spacing=1)
            if not hide_c:
                ux = x_pos + num_w + spacing
                uy = OFFSET_Y + max(0, (avail_h - 8 * unit_scale) // 2)
                oled.text_scaled('C', ux, uy, scale=unit_scale, col=1, spacing=1)
            oled.show()
            last_update = now
        time.sleep_ms(100)

if __name__ == "__main__":
    main()

