import wave
import math
import sound
import ui
from datetime import datetime
import location

# Constants
SAMPLE_RATE = 96000
BAUD_RATE = 300
MARK_TONE = 1800
SPACE_TONE = 1600
DURATION_PER_BIT = SAMPLE_RATE // BAUD_RATE
FLAG = 0x7E
POLY = 0x8408
PREAMBLE_LENGTH = 32

def highpass_filter(data, cutoff=350):
    RC = 1.0 / (cutoff * 2 * math.pi)
    alpha = RC / (RC + 1.0 / SAMPLE_RATE)
    filtered_data = []
    prev_sample = 0.0
    for sample in data:
        filtered_sample = alpha * (prev_sample + sample - (filtered_data[-1] if filtered_data else sample))
        filtered_data.append(int(filtered_sample))
        prev_sample = sample
    return filtered_data

def encode_callsign(callsign, ssid=0):
    callsign = callsign.ljust(6)[:6].upper()
    encoded = bytearray((ord(c) << 1) for c in callsign)
    encoded.append((ssid << 1) | 0x60)
    return encoded

def ax25_frame(source, destination, path, info):
    frame = bytearray()
    frame.extend(encode_callsign(destination, 0))
    frame.extend(encode_callsign(source, 0))
    for call in path:
        frame.extend(encode_callsign(call, 0))
    frame[-1] |= 0x01
    frame.extend(b'\x03\xf0')
    frame.extend(info.encode('ascii'))
    crc = crc16_ccitt(frame)
    frame.extend(crc.to_bytes(2, 'little'))
    ax25_packet = bytearray([FLAG] * PREAMBLE_LENGTH) + frame + bytearray([FLAG])
    return ax25_packet

def crc16_ccitt(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ POLY
            else:
                crc >>= 1
    return crc ^ 0xFFFF

def format_coordinates(latitude, longitude, symbol='/'):
    lat_deg = int(abs(latitude))
    lat_min = (abs(latitude) - lat_deg) * 60
    lat_hemisphere = 'N' if latitude >= 0 else 'S'
    lat_str = f"{lat_deg:02}{lat_min:05.2f}{lat_hemisphere}"

    lon_deg = int(abs(longitude))
    lon_min = (abs(longitude) - lon_deg) * 60
    lon_hemisphere = 'E' if longitude >= 0 else 'W'
    lon_str = f"{lon_deg:03}{lon_min:05.2f}{lon_hemisphere}"

    position_str = f"{lat_str}{symbol}{lon_str}"
    return position_str

def generate_continuous_tone(frequency, samples, phase=0, amplitude=0.02):
    tone = []
    for t in range(samples):
        sample = amplitude * 32767 * math.sin(2 * math.pi * frequency * t / SAMPLE_RATE + phase)
        tone.append(int(sample))
    phase += (2 * math.pi * frequency * samples / SAMPLE_RATE) % (2 * math.pi)
    return tone, phase

def afsk_encode(packet):
    audio = []
    phase = 0
    bitstream = generate_bitstream(packet)
    current_tone = None

    for bit in bitstream:
        if bit == 1:
            if current_tone != MARK_TONE:
                current_tone = MARK_TONE
            tone, phase = generate_continuous_tone(MARK_TONE, DURATION_PER_BIT, phase, amplitude=0.02)
        else:
            if current_tone != SPACE_TONE:
                current_tone = SPACE_TONE
            tone, phase = generate_continuous_tone(SPACE_TONE, DURATION_PER_BIT, phase, amplitude=0.02)
        
        audio.extend(tone)

    max_amplitude = max(abs(sample) for sample in audio)
    if max_amplitude > 0:
        audio = [int(sample * (32767 / max_amplitude)) for sample in audio]
    audio = highpass_filter(audio)
    return audio

def generate_bitstream(packet):
    bitstream = []
    for _ in range(PREAMBLE_LENGTH):
        bitstream.extend([0, 1])

    prev_bit = 1
    for byte in packet:
        for i in range(8):
            bit = (byte >> i) & 1
            if bit == 0:
                prev_bit ^= 1
            bitstream.append(prev_bit)

    bitstream.extend([0, 1])
    return bitstream

def save_to_wav(audio, filename):
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_data = bytearray()
        for sample in audio:
            wav_data.extend(int(sample).to_bytes(2, byteorder='little', signed=True))
        wav_file.writeframes(wav_data)

def play_audio(filename):
    sound.play_effect(filename)

def get_current_coordinates():
    location.start_updates()
    loc = location.get_location()
    location.stop_updates()
    latitude = loc['latitude']
    longitude = loc['longitude']
    return latitude, longitude

class APRSGUI(ui.View):
    def __init__(self):
        self.setup_view()
    
    def setup_view(self):
        self.play_button = ui.Button(title="Play APRS", font=('Helvetica', 30), action=self.play_aprs)
        self.play_button.center = (self.width * 0.5, self.height * 0.5)
        self.play_button.flex = 'WH'
        self.add_subview(self.play_button)
    
    def play_aprs(self, sender):
        latitude, longitude = get_current_coordinates()
        position_report = format_coordinates(latitude, longitude, '/')
        timestamp = datetime.utcnow().strftime("%d%H%Mz")
        info = f"@{timestamp}{position_report}(KO4GOF Testing 300 baud app on pythonista 2"
        packet = ax25_frame('YourCall', 'IOSPY1', ['WIDE1', 'WIDE2'], info)
        audio_signal = afsk_encode(packet)
        filename = f"aprs{datetime.now().strftime('%m%d%Y%H%M%S')}.wav"
        save_to_wav(audio_signal, filename)
        play_audio(filename)

view = APRSGUI()
view.present('fullscreen')
