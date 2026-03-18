#!/usr/bin/env python3
"""
csi_reader.py - PoC script for reading raw WiFi CSI data from ESP32
RF Sensing Physical AI Platform - T5
Author: TECH MANAGER
Date: 2026-03-18

Requirements:
    pip install pyserial numpy

Usage:
    python csi_reader.py --port /dev/ttyUSB0 --output csi_raw_data.csv
"""

import serial
import numpy as np
import argparse
import json
import time
from datetime import datetime

# Default config
DEFAULT_PORT = '/dev/ttyUSB0'  # Linux; Windows: 'COM3'; Mac: '/dev/tty.usbserial-*'
DEFAULT_BAUD = 115200
DEFAULT_OUTPUT = 'csi_raw_data.csv'
SUBCARRIERS_HT40 = 52  # Expected subcarrier count for 802.11n HT40


def parse_csi_line(line: str) -> dict | None:
    """
    Parse a CSI_DATA line from ESP32 serial output.
    Format: CSI_DATA,len,mac,rssi,rate,sig_mode,mcs,bandwidth,
            smoothing,not_sounding,aggregation,stbc,fec_coding,sgi,
            noise_floor,ampdu_cnt,channel,secondary_channel,timestamp,
            ant,sig_len,rx_state,len,first_word,data[...]
    """
    line = line.strip()
    if not line.startswith('CSI_DATA'):
        return None

    parts = line.split(',')
    if len(parts) < 25:
        return None

    try:
        # Parse raw CSI data (imaginary + real interleaved pairs)
        raw_data = list(map(int, parts[25:]))
        if len(raw_data) < 2:
            return None

        # Build complex values: [imag0, real0, imag1, real1, ...]
        csi_complex = [
            complex(raw_data[i+1], raw_data[i])
            for i in range(0, len(raw_data) - 1, 2)
        ]

        amplitude = np.abs(csi_complex).tolist()
        phase = np.angle(csi_complex).tolist()

        return {
            'timestamp_esp': int(parts[18]),
            'timestamp_host': datetime.now().isoformat(),
            'rssi': int(parts[4]),
            'mcs': int(parts[7]),
            'bandwidth': int(parts[8]),  # 0=20MHz, 1=40MHz
            'channel': int(parts[16]),
            'secondary_channel': int(parts[17]),
            'noise_floor': int(parts[15]),
            'subcarriers': len(amplitude),
            'amplitude': amplitude,
            'phase': phase,
            'raw_len': int(parts[1])
        }
    except (ValueError, IndexError) as e:
        return None


def validate_csi(parsed: dict) -> bool:
    """Validate CSI data quality."""
    if parsed['subcarriers'] < SUBCARRIERS_HT40:
        return False
    if parsed['rssi'] < -90:
        return False
    if all(a == 0 for a in parsed['amplitude']):
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description='ESP32 CSI Reader - RF Sensing PoC')
    parser.add_argument('--port', default=DEFAULT_PORT, help='Serial port')
    parser.add_argument('--baud', type=int, default=DEFAULT_BAUD, help='Baud rate')
    parser.add_argument('--output', default=DEFAULT_OUTPUT, help='Output CSV file')
    parser.add_argument('--samples', type=int, default=0, help='Max samples (0=infinite)')
    args = parser.parse_args()

    print(f'[CSI READER] RF Sensing Platform - T5 PoC')
    print(f'[CSI READER] Port: {args.port} @ {args.baud} baud')
    print(f'[CSI READER] Output: {args.output}')
    print(f'[CSI READER] Expected subcarriers: {SUBCARRIERS_HT40} (HT40)')
    print('-' * 60)

    try:
        ser = serial.Serial(args.port, args.baud, timeout=2)
    except serial.SerialException as e:
        print(f'[ERROR] Cannot open port {args.port}: {e}')
        print('[HINT] Try: sudo chmod 666 /dev/ttyUSB0')
        return

    count = 0
    valid_count = 0
    start_time = time.time()

    with open(args.output, 'w') as f:
        # Write CSV header
        f.write('timestamp_host,timestamp_esp,rssi,channel,subcarriers,amplitude,phase\n')

        while True:
            try:
                line = ser.readline().decode('utf-8', errors='ignore')
                parsed = parse_csi_line(line)

                if parsed:
                    count += 1
                    if validate_csi(parsed):
                        valid_count += 1
                        f.write(
                            f"{parsed['timestamp_host']},"
                            f"{parsed['timestamp_esp']},"
                            f"{parsed['rssi']},"
                            f"{parsed['channel']},"
                            f"{parsed['subcarriers']},"
                            f"{json.dumps(parsed['amplitude'])},"
                            f"{json.dumps(parsed['phase'])}\n"
                        )
                        f.flush()

                    if count % 100 == 0:
                        elapsed = time.time() - start_time
                        rate = count / elapsed
                        print(
                            f'[OK] Samples: {count} (valid: {valid_count}) | '
                            f'RSSI: {parsed["rssi"]} dBm | '
                            f'Subcarriers: {parsed["subcarriers"]} | '
                            f'Rate: {rate:.1f} Hz | '
                            f'Channel: {parsed["channel"]}'
                        )

                if args.samples > 0 and count >= args.samples:
                    print(f'[DONE] Collected {count} samples ({valid_count} valid).')
                    break

            except KeyboardInterrupt:
                print(f'\n[STOP] User interrupted. Total: {count} samples ({valid_count} valid).')
                break
            except Exception as e:
                print(f'[WARN] Parse error: {e}')
                continue

    ser.close()
    elapsed = time.time() - start_time
    print(f'[DONE] Saved to {args.output} | Duration: {elapsed:.1f}s | Valid rate: {valid_count/max(count,1)*100:.1f}%')


if __name__ == '__main__':
    main()
