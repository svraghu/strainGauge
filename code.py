import time
import board
import busio

# ---------------- ADS1115 Definitions -------------------------
ADS1115_ADDRESS    = 0x48
CONVERSION_REG     = 0x00
CONFIG_REG         = 0x01

# ---------------- User Config: Gain Setting -------------------
# Choose a gain setting: one of "2/3", "1", "2", "4", "8", or "16".
# For differential mode, this determines the full-scale voltage.
gain_setting = "16"  # For example, "1" gives ±4.096 V full-scale

# Gain mapping: PGA bits and full-scale voltage in Volts.
gain_map = {
    "2/3": {"pga_bits": 0b000, "fs_voltage": 6.144},
    "1":   {"pga_bits": 0b001, "fs_voltage": 4.096},
    "2":   {"pga_bits": 0b010, "fs_voltage": 2.048},
    "4":   {"pga_bits": 0b011, "fs_voltage": 1.024},
    "8":   {"pga_bits": 0b100, "fs_voltage": 0.512},
    "16":  {"pga_bits": 0b101, "fs_voltage": 0.256},
}
if gain_setting not in gain_map:
    raise ValueError("Invalid gain setting. Choose from: " + ", ".join(gain_map.keys()))

pga_bits = gain_map[gain_setting]["pga_bits"]
fs_voltage = gain_map[gain_setting]["fs_voltage"]  # in Volts

# Data rate: use 128 SPS (dr_bits = 0b100)
dr_bits = 0b100

# Calculate the LSB (volts per bit):
LSB = fs_voltage / 32767   # 16-bit ADC; maximum positive bit is 32767

print("Testing ADS1115 in differential mode (A0-A1)")
print("Gain setting:", gain_setting)
print("Full-scale voltage: {:.3f} V".format(fs_voltage))
print("LSB (V/bit): {:.8f}".format(LSB))
expected_adc = 0.100 / LSB
print("Expected raw ADC for 100 mV input: {:.0f}".format(expected_adc))
print("--------------------------------------------")

# ---------------- Build ADS1115 Configuration ---------------------
# For differential measurement between A0 and A1:
#   OS:        1 << 15         (start conversion; ignored in continuous mode)
#   MUX:       0b000 << 12     (differential: A0-A1)
#   PGA:       pga_bits << 9   (set by gain_map)
#   MODE:      0 << 8          (continuous conversion)
#   DR:        dr_bits << 5    (128 SPS)
#   COMP_QUE:  0b11            (disable comparator)
config_word = (1 << 15) | (0b000 << 12) | (pga_bits << 9) | (0 << 8) | (dr_bits << 5) | 0b11
config_high = (config_word >> 8) & 0xFF
config_low  = config_word & 0xFF

# ---------------- I2C Initialization -----------------------------
# Use the confirmed working pins: board.IO9 for SCL and board.IO8 for SDA.
i2c = busio.I2C(board.IO9, board.IO8, frequency=100000)
while not i2c.try_lock():
    pass

devices = i2c.scan()
print("I2C devices found:", [hex(dev) for dev in devices])
if ADS1115_ADDRESS not in devices:
    print("Error: ADS1115 not detected on the I2C bus!")
    i2c.unlock()
    raise RuntimeError("ADS1115 not detected.")

# ---------------- Write Configuration to ADS1115 --------------------
try:
    # Write the configuration register address (CONFIG_REG) followed by configuration bytes.
    data = bytes([CONFIG_REG, config_high, config_low])
    i2c.writeto(ADS1115_ADDRESS, data)
    print("Configuration written: [{:02X}, {:02X}, {:02X}]".format(CONFIG_REG, config_high, config_low))
except OSError as e:
    print("I2C error during configuration:", e)
    i2c.unlock()
    raise

time.sleep(0.2)  # Allow time for conversion to settle
i2c.unlock()

# ---------------- Main Loop: Read and Convert ----------------------
while True:
    try:
        while not i2c.try_lock():
            pass
        # Set pointer to the conversion register.
        i2c.writeto(ADS1115_ADDRESS, bytes([CONVERSION_REG]))
        result = bytearray(2)
        i2c.readfrom_into(ADS1115_ADDRESS, result)
        i2c.unlock()
    except OSError as e:
        print("I2C error during read:", e)
        time.sleep(1)
        continue

    # Combine the two bytes into a signed 16-bit integer.
    raw_value = (result[0] << 8) | result[1]
    if raw_value & 0x8000:
        raw_value -= (1 << 16)

    # Convert raw ADC value to measured voltage (in Volts)
    measured_voltage = raw_value * LSB
    voltage_mV = measured_voltage * 1000  # convert to mV

    # For your sensor (after conditioning), assume a linear mapping: 1 mV = 1 psig.
    psig = voltage_mV
#    if psig < 0:
#        psig = 0
#    if psig > 100:
#        psig = 100

    print("Raw ADC:", raw_value,
          "Voltage: {:.3f} mV".format(voltage_mV),
          "Pressure: {:.1f} psig".format(psig))
    time.sleep(1)