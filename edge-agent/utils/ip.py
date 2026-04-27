import socket
import uuid


def get_mac_address():
    """获取设备的真实物理常驻 MAC 地址作为默认唯一硬件标识"""
    mac_num = hex(uuid.getnode()).replace('0x', '').replace('L', '').zfill(12).upper()
    return '-'.join(mac_num[i: i + 2] for i in range(0, 12, 2))


def get_local_ip_address():
    """
    获取当前设备可用的本机 IPv4 地址（优先局域网地址）。
    如果无法探测，回退到 127.0.0.1。
    """
    # 首选：通过 UDP 套接字获取默认出口网卡 IP（不会真正发包）
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    # 次选：从主机名解析结果中选择第一个非回环地址
    try:
        _, _, ips = socket.gethostbyname_ex(socket.gethostname())
        for ip in ips:
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"