#!/usr/bin/env python3
"""Generate four lesson QR PNG files after Netlify URL is known.
Usage: pip install "qrcode[pil]" && python tools/generate_qr.py https://example.netlify.app
"""
from pathlib import Path
from urllib.parse import urlparse
import sys

try:
    import qrcode
except ImportError:
    raise SystemExit('먼저 pip install "qrcode[pil]" 를 실행하세요.')

def main():
    if len(sys.argv) != 2:
        raise SystemExit('사용법: python tools/generate_qr.py https://내사이트.netlify.app')
    base=sys.argv[1].strip().rstrip('/')
    parsed=urlparse(base)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path not in ('','/'):
        raise SystemExit('https://호스트명 (경로 없는 Netlify 사이트 주소)를 입력해주세요.')
    out=Path('qr-output')
    out.mkdir(parents=True,exist_ok=True)
    items={'통합홈':'/','2차시_파워셸':'/02/','3차시_시뮬레이터':'/03/','4차시_코랩':'/04/','5차시_대시보드':'/05/'}
    lines=[]
    for name,path in items.items():
        url=base+path
        q=qrcode.QRCode(version=None,error_correction=qrcode.constants.ERROR_CORRECT_H,box_size=14,border=4)
        q.add_data(url);q.make(fit=True)
        img=q.make_image(fill_color='black',back_color='white')
        img.save(out/(name+'.png'))
        print(name+': '+url)
        lines.append(name+': '+url)
    (out/'QR_최종URL.txt').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('QR 파일 위치:',out.resolve())

if __name__=='__main__': main()
