# SMC Laser Chiller Documentation

## Overview

The SMC Laser Chiller is a device used to maintain a stable temperature for various industrial and scientific applications. This documentation provides a summary of the communication protocol used to interface with the chiller, including command codes, control codes, and the format for sending and receiving data.

## Communication Protocol

### Specifications

- Standards: RS-485 or RS-232C
- Circuit Type: Half duplex
- Communication Type: Asynchronous
- Communication Speed: Changeable; options include 600, 1200 (Default), 2400, 4800, 9600, 19200 bps
- Character Code: ASCII
- Parity: none.
- Start Bit: 1 bit
- Data Length: 8 bits
- Stop Bit: 1 bit
- Block Check: Sum check

## Control Codes

The following ASCII codes are used for communication control:

| Command | ASCII | Description       |
|---------|-------|-------------------|
| ENQ     | 05H   | Enquiry           |
| STX     | 02H   | Start of Text     |
| ETX     | 03H   | End of Text       |
| ACK     | 06H   | Acknowledge       |
| CR      | 0DH   | Carriage Return   |
| SOH     | 01H   | Start of Header   |

## Command Codes

The following command codes are used for various operations:

| Command | Description                           |
|---------|---------------------------------------|
| 31H     | Set temperature (without writing to FRAM) |
| 32H     | Read internal sensor                   |
| 33H     | Read external sensor                   |
| 34H     | Read alarm status                      |
| 36H     | Set offset (without writing to FRAM)   |
| 37H     | Set temperature (with writing to FRAM)  |
| 38H     | Set offset (with writing to FRAM)      |

## Communication Format

### Setting Temperature (without FRAM)

- Host: STX 31H Setting data ETX Checksum CR
- Thermo-con: ACK CR
- Example: Setting temperature to 25.0°C
- Host: 02 31 32 35 30 30 03 3F 38 0D
- Thermo-con: 06 0D

### Reading Internal Sensor

- Host: ENQ 32H Checksum CR
- Thermo-con: STX 32H Internal sensor ETX Checksum CR
- Host: ACK CR (optional)
- Example: Reading internal sensor temperature
- Host: 05 32 33 32 0D
- Thermo-con: 02 32 32 35 30 32 03 3F 3B 0D

### Reading External Sensor

- Host: ENQ 33H Checksum CR
- Thermo-con: STX 33H External sensor ETX Checksum CR
- Host: ACK CR (optional)
- Example: Reading external sensor temperature
- Host: 05 33 33 33 0D
- Thermo-con: 02 33 33 30 30 32 03 3F 38 0D

### Reading Alarm Status

- Host: ENQ 34H Checksum CR
- Thermo-con: STX 34H Data ETX Checksum CR
- Host: ACK CR (optional)
- Example: Reading alarm status
- Host: 05 34 33 34 0D
- Thermo-con: 02 34 30 38 30 03 3C 3C 0D

## Calculating Checksum

The checksum is calculated by summing all bytes from the second byte to ETX. Only the lower 1 byte of the sum is used.

- Example: Setting temperature to 30.0°C (without unit specified)
- Command: STX 31H 33H 30H 30H 30H ETX
- Sum: F4H
- Checksum: 34H

## Communication Procedures

1. Setting Change: Initiated by the host, returns ACK from Thermo-con if successful.
2. Confirming and Reading: Initiated by the host, returns the requested data from Thermo-con.
3. Unit Specification: If multiple Thermo-cons are used, specify unit numbers to avoid data conflicts.

## Troubleshooting

Common issues and solutions include:

- Wrong Connecting Cable: Use straight cable for RS-485 and cross cable for RS-232C.
- Settings Mismatch: Ensure host and Thermo-con settings match (Unit Number, Baud Rate, Parity Bit, Data Length, Stop Bit).
- Incorrect Program: Follow the operation manual for proper control codes, command codes, and checksum.
- Noise Interference: Use shielded cables and ground the shield to FG.
- Reflected Wave Interference: Set terminating resistance.

## Important Notes

- Ensure communication settings are correct before starting.
- Check for proper grounding and use of shielded cables.
- Follow the specified procedures for setting and reading data to avoid communication errors.
- Validate connections and settings regularly to maintain reliable operation.
