#!/usr/bin/python
# -*- coding: utf-8 -*-

import glob,os,struct
import binascii

# This script analyzes a folder structure, which was generated by the unpack
# script. It tries to provide information about the firmware (Server, Extensions)
# - filename of the firmware
# - CPU for the firmware
# - ROM area used
# - RAM area used
# - Category (Server,Legacy,Tree,NAT or Air)
# - Version number of the firmware version
# - Product name

# RC6 encryption/decryption <https://en.wikipedia.org/wiki/RC6>
def ROR(x, n, bits=32):
  """rotate right input x, by n bits"""
  mask = (2L**n) - 1
  mask_bits = x & mask
  return (x >> n) | (mask_bits << (bits - n))
def ROL(x, n, bits=32):
  """rotate left input x, by n bits"""
  return ROR(x, bits - n,bits)
def RC6_PrepareKey(str):
  key = 0
  for c in str:
    key += ord(c)
  return key | 0xFEED0000
def RC6_GenerateKey(initKey):
  """generate key s[0... 2r+3] from given input userkey"""
  L = (((initKey << 8) & 0x100) | (initKey << 24) | (initKey >> 24) | ((initKey >> 8) & 0x10)) & 0xFFFFFFFF
  r=16 # rounds
  w=32 # width in bits
  modulo = 2**32
  context_s=(2*r+4)*[0]
  context_s[0]=0xB7E15163
  for i in range(1,2*r+4):
    context_s[i]=(context_s[i-1]+0x9E3779B9)%(2**w)
  l = [L]
  enlength = 1
  v = 3*max(enlength,2*r+4)
  A=B=i=j=0
  for index in range(0,v):
    A = context_s[i] = ROL((context_s[i] + A + B)%modulo,3)
    B = l[j] = ROL((l[j] + A + B)%modulo,(A+B)%32) 
    i = (i + 1) % (2*r + 4)
    j = (j + 1) % enlength
  return context_s
def RC6_EncryptBlock(context,encoded):
  A,B,C,D = struct.unpack('<IIII', encoded)
  r=16
  w=32
  modulo = 2**32
  lgw = 5
  C = (C - context[2*r+3])%modulo
  A = (A - context[2*r+2])%modulo
  for j in range(1,r+1):
    i = r+1-j
    (A, B, C, D) = (D, A, B, C)
    u_temp = (D*(2*D + 1))%modulo
    u = ROL(u_temp,lgw)
    t_temp = (B*(2*B + 1))%modulo 
    t = ROL(t_temp,lgw)
    tmod=t%32
    umod=u%32
    C = (ROR((C-context[2*i+1])%modulo,tmod)  ^u)  
    A = (ROR((A-context[2*i])%modulo,umod)   ^t) 
  D = (D - context[1])%modulo 
  B = (B - context[0])%modulo
  return struct.pack('<IIII', A,B,C,D)
def RC6_DecryptBlock(context,encoded):
  A,B,C,D = struct.unpack('<IIII', encoded)
  r=16
  w=32
  modulo = 2**32
  lgw = 5
  B = (B + context[0])%modulo
  D = (D + context[1])%modulo 
  for i in range(1,r+1):
    t_temp = (B*(2*B + 1))%modulo 
    t = ROL(t_temp,lgw)
    u_temp = (D*(2*D + 1))%modulo
    u = ROL(u_temp,lgw)
    tmod=t%32
    umod=u%32
    A = (ROL(A^t,umod) + context[2*i])%modulo 
    C = (ROL(C^u,tmod) + context[2*i+ 1])%modulo
    (A, B, C, D)  =  (B, C, D, A)
  A = (A + context[2*r + 2])%modulo 
  C = (C + context[2*r + 3])%modulo
  return struct.pack('<IIII', A,B,C,D)
def RC6_Encrypt(context,data):
  blockSize = 16
  data += '\0' * (blockSize-1)
  data = data[:(len(data) / blockSize) * blockSize]
  result = ''
  for block in [data[i:i+blockSize] for i in range(0, len(data), blockSize)]:
    result += RC6_EncryptBlock(context,block)
  return result
def RC6_Decrypt(context,data):
  blockSize = 16
  result = ''
  for block in [data[i:i+blockSize] for i in range(0, len(data), blockSize)]:
    result += RC6_DecryptBlock(context,block)
  return result

def versionStr(version):
  v1 = version / 1000000
  v2 = ((version / 10000) % 100)
  v3 = ((version / 100) % 100)
  v4 = (version % 100)
  return '%d.%d.%d.%d' % (v1,v2,v3,v4)
def productBySubID(devType):
  # Loxone Link extensions:
  if devType==0x0001: return "Air Base Extension V2"
  elif devType==0x0004: return "DMX Extension V2"
  elif devType==0x0005: return "1-Wire Extension V2"
  elif devType==0x0006: return "RS232 Extension V2"
  elif devType==0x0007: return "RS485 Extension V2"
  elif devType==0x0009: return "Modbus Extension V2"
  elif devType==0x000a: return "RGBW 24V Dimmer V2"
  elif devType==0x000B: return "Relay Extension V2"
  elif devType==0x000F: return "Fröling Extension V2"
  elif devType==0x0012: return "Internorm Extension"
  elif devType==0x0013: return "Tree Extension"
  elif devType==0x0014: return "DI Extension"
  elif devType==0x0015: return "KNX Extension"
  elif devType==0x0016: return "AI Extension"
  elif devType==0x0017: return "AO Extension"
  # Bit 15 set => Tree Bus devices
  elif devType==0x8001: return "Valve Tree"
  elif devType==0x8002: return "Motion Sensor Tree"
  elif devType==0x8003: return "Touch Tree"
  elif devType==0x8004: return "Universal Tree"
  elif devType==0x8005: return "Touch Pure Tree"
  elif devType==0x8006: return "Corridor Light Tree"
  elif devType==0x8007: return "Ceiling Spot RGBW Tree"
  elif devType==0x8008: return "Downlight Spot RGBW Tree"
  elif devType==0x8009: return "Keypad Tree"
  elif devType==0x800A: return "Weather Station Tree"
  elif devType==0x800B: return "Nano DI Tree"
  elif devType==0x800C: return "RGBW Dimmer Tree"
  elif devType==0x800D: return "TouchStone Tree"
  elif devType==0x800E: return "Ceiling Spot WW Tree"
  elif devType==0x800F: return "Downlight Spot WW Tree"
  elif devType==0x8010: return "Roomsensor Tree"
  elif devType==0x8011: return "Pendant Light RGBW Tree"
  elif devType==0x8012: return "Alarmsiren Tree"
  elif devType==0x8013: return "Damper Tree"
  elif devType==0x8014: return "Leaf Tree"
  elif devType==0x8015: return "Window Integral Tree"
  elif devType==0x8016: return "Rds Spot RGBW Tree"
  elif devType==0x8017: return "Rds Spot WW Tree"
  elif devType==0x8018: return "Power Tree"
  elif devType==0x8019: return "Nano Relay 2 Tree"
  return "treeDev[0x%04X]" % devType

def productToProductName(product):
  if product == 'AirBase': return 'Air Base Extension'
  elif product == 'AmbientLight': return 'Touch Nightlight Air'
  elif product == 'BackwashValve': return 'AquaStar Air'
#  elif product == 'CapTouch': return 'CapTouch'
  elif product == 'CorridorLightAir': return 'Corridor Light Air'
  elif product == 'FirealarmAir': return 'Smoke Detector Air'
  elif product == 'GeigerRemote': return 'GEIGER Remote LC Air'
  elif product == 'IrAir': return 'IR Control Air'
  elif product == 'KeypadAir': return 'NFC Code Touch Air'
  elif product == 'InternormFanAir': return 'Internorm Fan Air'
  elif product == 'LeafAir': return 'Leaf 1 Air'
  elif product == 'LeafTouchAir': return 'Leaf Switch Sensor'
  elif product == 'MeterInt': return 'Meter Reader IR Air'
  elif product == 'MultiExtensionAir': return 'Multi Extension Air'
  elif product == 'NanoDimmer_Touch': return 'Nano Dimmer Air'
  elif product == 'NanoIO_Keypad': return 'Nano IO NFC Code Touch Air'
  elif product == 'NanoIO_Touch': return 'Nano IO Touch Air'
  elif product == 'Noisemaker': return 'Alarm Siren Air'
  elif product == 'PendantLightRgbwAir': return 'Pendant Light RGBW Air'
  elif product == 'PresenceAir': return 'Motion Sensor'
  elif product == 'RemoteAir': return 'Remote Air'
  elif product == 'RgbwDimmerAir': return 'RGBW 24V Dimmer'
  elif product == 'Roomsensor': return 'Temperature & Humidity Sensor Air'
  elif product == 'RoomsensorCO2': return 'Room Comfort Sensor Air'
  elif product == 'RoomsensorAir': return 'Roomsensor Air'
  elif product == 'ShadeActuatorAir': return 'Shading Actuator Air'
#  elif product == 'ShelfControl': return 'ShelfControl'
  elif product == 'SmartSocketAir': return 'Smart Socket Air'
#  elif product == 'SocketDimmerSeparator': return 'SocketDimmerSeparator'
  elif product == 'SteakThermo': return 'Touch & Grill Air'
  elif product == 'TouchPureAir': return 'Touch Pure Air'
  elif product == 'TouchPureAir_V2': return 'Touch Pure Air V2'
  elif product == 'TouchStoneAir': return 'Touch Surface Air'
  elif product == 'TubemotorAir': return 'GEIGER SOLIDline Air'
  elif product == 'ValveAir': return 'Loxone Valve Actuator Air'
  elif product == 'VenBlindmotorAir': return 'GEIGER Blind Motor GJ56 Air'
  elif product == 'VentAir': return 'Damper Air'
  elif product == 'WaterSensor': return 'Water Sensor Air'
  elif product == 'WeatherStationAir': return 'Weather Station Air'
  elif product == 'WindowHandle': return 'Window Handle Air'
  elif product == 'WindowIntegralAir': return 'Window Integral Air'
  elif product == 'WindowSensor': return 'Door & Window Contact Air'
  elif product == 'ZipmotorAir': return 'GEIGER SOLIDline Zip Air'

  elif product == 'LoxC1WR': return '1-Wire Extension'
  elif product == 'LoxCDMX': return 'DMX Extension'
  elif product == 'LoxCENO': return 'EnOcean Extension'
  elif product == 'LoxCREL': return 'Relay Extension'
  elif product == 'LoxDALI': return 'DALI Extension'
  elif product == 'LoxDIMM': return 'Dimmer Extension'
  elif product == 'LoxDIMM_V2': return 'Dimmer Extension V2'
  elif product == 'LoxFroeling': return 'Fröling Extension'
  elif product == 'LoxIR': return 'IR Extension'
  elif product == 'LoxMORE': return 'Extension'
  elif product == 'LoxC232': return 'RS232 Extension'
  elif product == 'LoxC485': return 'RS485 Extension'
  elif product == 'LoxI485': return 'IR Extension'
  elif product == 'LoxModbus232': return 'Modbus RS232 Extension'
  elif product == 'LoxModbus485': return 'Modbus Extension'
  elif product == 'Miniserver': return 'Miniserver'
  return None

def productByFilename(filename):
  filename,extension = filename.split('.')
  version,product = filename.split('_',1)
  productName = productToProductName(product)
  if productName:
    return productName
  RC6context = RC6_GenerateKey(0x254A21) # a constant for firmware name names
  encryptedBlock = binascii.unhexlify(product)
  product = RC6_Decrypt(RC6context,encryptedBlock).rstrip('\0')
  productName = productToProductName(product)
  if productName:
    return productName
  return product
# STM32 CRC32 calculation, e.g. used for updates. Always 4 byte-aligned packages!
stm32_crc_table = {}
def generate_stm32_crc32_table():
    global stm32_crc_table
    poly=0x04C11DB7
    for i in range(256):
        c = i << 24
        for j in range(8):
            c = (c << 1) ^ poly if (c & 0x80000000) else c << 1
        stm32_crc_table[i] = c & 0xffffffff
generate_stm32_crc32_table()
def stm32_crc32(bytes_arr):
  length = len(bytes_arr)
  crc = 0xffffffff
  k = 0
  while length > 0:
    v = 0
    v |= ((bytes_arr[k+0] << 24) & 0xFF000000)
    if length > 1:
      v |= ((bytes_arr[k+1] << 16) & 0x00FF0000)
    if length > 2:
      v |= ((bytes_arr[k+2] <<  8) & 0x0000FF00)
    if length > 3:
      v |= ((bytes_arr[k+3] <<  0) & 0x000000FF)
    crc = ((crc << 8) & 0xffffffff) ^ stm32_crc_table[0xFF & ((crc >> 24) ^ v)]
    crc = ((crc << 8) & 0xffffffff) ^ stm32_crc_table[0xFF & ((crc >> 24) ^ (v >> 8))]
    crc = ((crc << 8) & 0xffffffff) ^ stm32_crc_table[0xFF & ((crc >> 24) ^ (v >> 16))]
    crc = ((crc << 8) & 0xffffffff) ^ stm32_crc_table[0xFF & ((crc >> 24) ^ (v >> 24))]
    k += 4
    length -= 4
  return crc

def analyzeUpdatefile(filename):
  f = open(filename, "rb")
  try:
      buffer = f.read()
      headerWord, = struct.unpack_from('<I', buffer,0)
      RAMBase = 0x20000000
      ROMProduct = None
      if headerWord == 0xc2c101ac:
        ROMBase = RAMBase
        RAMTop = RAMBase+128*1024*1024
        magic,ROMBlockCount,ROMVersion,ROMChecksum,ROMSizeCompressed,ROMSize = struct.unpack_from("<6L", buffer, 0)
        # the checksum is a trivial little endian XOR32 over the data
        ROMCalculatedChecksum = 0x00000000
        for offset in range(0x200, 0x200+ROMBlockCount*0x200, 4):
          ROMCalculatedChecksum ^= struct.unpack_from("<L", buffer, offset)[0]
        cpu = 'AT91SAM9G20'
        category = 'Server'
      else:
        headerLongs = struct.unpack_from('<128I',buffer,0)
        RAMTop = headerLongs[0]
        if headerLongs[7] == 0xfeedbeef:
          ROMSize = headerLongs[9]*4
          ROMChecksum = headerLongs[8]
          ROMVersion = headerLongs[10]
          ROMCalculatedChecksum = 0x00000000
          for offset in range(9, ROMSize/4):
            ROMCalculatedChecksum ^= struct.unpack_from("<L", buffer, offset*4)[0]
          if headerLongs[1] >= 0x1000 and headerLongs[1] < 0x00004000:
            cpu = 'LM3S2678'
            category = 'Legacy'
            ROMBase = headerLongs[1] & ~0x7FF
          elif headerLongs[1] >= 0x08000000 and headerLongs[1] < 0x08004000:
            cpu = 'ZWIR4502'
            category = 'Air'
            ROMBase = headerLongs[1] & ~0x7FF
        elif headerLongs[112] == 0xfeedbeef:
          ROMBase = headerLongs[1] & ~0x7FF
          ROMChecksum = headerLongs[113]
          ROMSize = headerLongs[114]*4
          ROMVersion = headerLongs[115]
          ROMProduct = headerLongs[116]
          b = bytearray()
          b.extend(buffer[114*4:])
          ROMCalculatedChecksum = stm32_crc32(b)
          cpu = 'STM32F3'
          if ROMProduct & 0x8000:
            category = 'Tree'
          else:
            category = 'NAT'
        else:
          print '### UNKNOWN ###',filename
          cpu = None
      if cpu:# and not productByFilename(filename) and not ROMProduct:
        infoStr = '%-80s' % (filename)
        infoStr += 'CPU:%-14s' % (cpu)
        infoStr += ' ROM:0x%08x-0x%08x ' % (ROMBase,ROMBase+ROMSize)
        infoStr += ' RAM:0x%08x-0x%08x' % (RAMBase,RAMTop)
        if ROMCalculatedChecksum:
          if ROMCalculatedChecksum != ROMChecksum:
            infoStr += ' ChecksumError:%#8.8x !- %#8.8x' % (ROMCalculatedChecksum,ROMChecksum)
        infoStr += ' Category:%-6s' % (category)
        infoStr += ' Version:%-10s' % (versionStr(ROMVersion))
        if ROMProduct:
          infoStr += ' product:"%s"' % (productBySubID(ROMProduct))
        productName = productByFilename(filename)
        if productName:
          infoStr += ' product name:"%s"' % (productName)
        print infoStr
  finally:
      f.close()

analyzeUpdatefile('10031111_Miniserver.upd')
os.chdir("./update")
for filename in sorted(glob.glob("*.upd")):
  analyzeUpdatefile(filename)
