import hmac, hashlib, base64, struct, time, json, sys
c = json.load(open('/home/z/my-project/aws/maa-user-credentials.json'))
pad = '=' * ((8 - len(c['totp_secret']) % 8) % 8)
key = base64.b32decode(c['totp_secret'].upper() + pad)
ctr = struct.pack('>Q', int(time.time()) // 30)
h = hmac.new(key, ctr, hashlib.sha1).digest()
o = h[19] & 0x0F
print(str((struct.unpack('>I', h[o:o+4])[0] & 0x7FFFFFFF) % 1000000).zfill(6))
