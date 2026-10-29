"""Generate printable QR PNG files after Netlify deployment.
Usage: python tools/create_qr.py https://YOUR_SITE.netlify.app
Requires: pip install qrcode[pil]
"""
import sys
from pathlib import Path
try:
 import qrcode
except ImportError:
 raise SystemExit('먼저 설치: pip install "qrcode[pil]"')
if len(sys.argv)!=2 or not sys.argv[1].startswith('https://'):
 raise SystemExit('사용법: python tools/create_qr.py https://YOUR_SITE.netlify.app')
root=Path(__file__).resolve().parents[1]/'QR_보고서용'
root.mkdir(exist_ok=True)
base=sys.argv[1].rstrip('/')
for key in ['home','02','03','04','05']:
 qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,box_size=12,border=4)
 qr.add_data(f'{base}/#{key}');qr.make(fit=True)
 qr.make_image(fill_color='black',back_color='white').save(root/f'AI_Vision_{key}.png')
print('생성 완료:',root)
