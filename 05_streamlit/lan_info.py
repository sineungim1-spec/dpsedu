from __future__ import annotations

import socket


def get_lan_ip() -> str:
    """현재 PC의 LAN IPv4 주소를 가능한 안정적으로 반환합니다.

    인터넷 연결이 없어도 Dashboard 실행 자체가 중단되지 않도록
    실패 시 hostname 기반 주소, 최종적으로 127.0.0.1을 반환합니다.
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # UDP connect는 실제 패킷 전송이 목적이 아니라
        # OS가 선택한 로컬 인터페이스 주소를 알아내기 위한 방법입니다.
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        if ip:
            return ip
    except Exception:
        pass
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip:
            return ip
    except Exception:
        pass

    return "127.0.0.1"
