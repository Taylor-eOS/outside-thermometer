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

    def measure_text(self, string):
        w_tmp = len(string) * 8
        h_tmp = 8
        if w_tmp == 0:
            return 0, -1, 0, -1, None, w_tmp, h_tmp
        buf_len = (w_tmp * h_tmp + 7) // 8
        buf = bytearray(buf_len)
        fbch = framebuf.FrameBuffer(buf, w_tmp, h_tmp, framebuf.MONO_HLSB)
        fbch.fill(0)
        fbch.text(string, 0, 0, 1)
        minx = w_tmp
        maxx = -1
        miny = h_tmp
        maxy = -1
        for yy in range(h_tmp):
            for xx in range(w_tmp):
                try:
                    if fbch.pixel(xx, yy):
                        if xx < minx: minx = xx
                        if xx > maxx: maxx = xx
                        if yy < miny: miny = yy
                        if yy > maxy: maxy = yy
                except Exception:
                    pass
        if maxx < minx or maxy < miny:
            return 0, -1, 0, -1, None, w_tmp, h_tmp
        return minx, maxx, miny, maxy, buf, w_tmp, h_tmp

    def draw_text_scaled(self, buf, tmp_w, tmp_h, minx, maxx, miny, maxy, x, y, scale=1, col=1):
        if buf is None or maxx < minx or maxy < miny:
            return 0, 0
        fbch = framebuf.FrameBuffer(buf, tmp_w, tmp_h, framebuf.MONO_HLSB)
        vis_w = maxx - minx + 1
        vis_h = maxy - miny + 1
        for yy in range(miny, maxy + 1):
            for xx in range(minx, maxx + 1):
                if fbch.pixel(xx, yy):
                    bx = x + (xx - minx) * scale
                    by = y + (yy - miny) * scale
                    for sy in range(scale):
                        py = by + sy
                        if py < 0 or py >= self.height:
                            continue
                        for sx in range(scale):
                            px = bx + sx
                            if px < 0 or px >= self.width:
                                continue
                            self.pixel(px, py, col)
        return vis_w * scale, vis_h * scale

    def text_scaled(self, string, x, y, scale=None, max_scale=None, col=1, spacing=1):
        if scale is None:
            scale = 1
        if max_scale is not None and scale > max_scale:
            scale = max_scale
        minx, maxx, miny, maxy, buf, tmp_w, tmp_h = self.measure_text(string)
        if buf is None or maxx < minx or maxy < miny:
            return 0
        if scale == 1:
            self.text(string, x, y, col)
            return maxx - minx + 1
        self.draw_text_scaled(buf, tmp_w, tmp_h, minx, maxx, miny, maxy, x, y, scale, col)
        return (maxx - minx + 1) * scale

    def fill_rect(self, x, y, w, h, col=1):
        if w <= 0 or h <= 0:
            return
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                self.pixel(xx, yy, col)

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
    DISPLAY_UPDATE_MS = 10000
    DUMP_INTERVAL_MS = 5000
    RECV_BLINK_MS = 250
    sda_pin = SDA_PIN
    scl_pin = SCL_PIN
    i2c = I2C(I2C_ID, sda=Pin(sda_pin), scl=Pin(scl_pin))
    scan_i2c(i2c)
    oled = SSD1306_I2C(128, 64, i2c, addr=I2C_ADDR)
    oled.contrast(255)
    channel = 1
    e = init_espnow(channel)
    last_update = time.ticks_ms()
    last_dump = time.ticks_ms()
    last_recv = time.ticks_ms() - 10000
    recv_blink_until = time.ticks_ms() - 10000
    temp = 0.0

    def update_display(now):
        oled.fill(0)
        num_str = '{:.1f}'.format(temp)
        minx_n, maxx_n, miny_n, maxy_n, buf_n, tmp_w_n, tmp_h_n = oled.measure_text(num_str)
        if maxx_n < minx_n:
            vis_w = 0
            vis_h = 0
        else:
            vis_w = maxx_n - minx_n + 1
            vis_h = maxy_n - miny_n + 1
        avail_w = oled.width - 2 * OFFSET_X
        avail_h = oled.height - 2 * OFFSET_Y
        if vis_w == 0:
            scale = 1
        else:
            max_scale_by_height = avail_h // max(1, vis_h)
            if max_scale_by_height < 1:
                max_scale_by_height = 1
            max_scale_by_width = avail_w // max(1, vis_w)
            if max_scale_by_width < 1:
                max_scale_by_width = 1
            scale = min(max_scale_by_height, max_scale_by_width)
            if scale < 1:
                scale = 1
        total_w = vis_w * scale
        x_pos = OFFSET_X + max(0, (avail_w - total_w) // 2)
        y_pos = OFFSET_Y + max(0, (avail_h - vis_h * scale) // 2)
        if vis_w:
            oled.draw_text_scaled(buf_n, tmp_w_n, tmp_h_n, minx_n, maxx_n, miny_n, maxy_n, x_pos, y_pos, scale, 1)
        oled.show()

    while True:
        if e.any():
            mac, data = e.recv()
            if data:
                temp_str = data.decode()
                print('Received:', repr(temp_str))
                try:
                    new_temp = float(temp_str)
                    temp = new_temp
                    print('Temperature updated to:', temp)
                    now = time.ticks_ms()
                    last_recv = now
                    update_display(now)
                    last_update = now
                except Exception as ex:
                    print('Error parsing temperature:', ex)
        now = time.ticks_ms()
        if time.ticks_diff(now, last_update) > DISPLAY_UPDATE_MS:
            update_display(now)
            last_update = now
        if time.ticks_diff(now, last_dump) > DUMP_INTERVAL_MS:
            print('DISPLAY_DUMP_START {}x{}'.format(oled.width, oled.height))
            for p in range(oled.pages):
                start = p * oled.width
                row = oled.buffer[1 + start:1 + start + oled.width]
                line = ''.join('{:02x}'.format(b) for b in row)
                print('PAGE {}: {}'.format(p, line))
            print('DISPLAY_DUMP_END')
            last_dump = now
        time.sleep_ms(50)

if __name__ == "__main__":
    main()

