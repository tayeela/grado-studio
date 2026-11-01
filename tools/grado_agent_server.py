#!/usr/bin/env python3
"""Отдельный локальный сервер ГРАДО для MCP, без рабочего каталога владельца.

Фиксированный loopback-порт; никакого автоперехода на порт основной программы.
Настройки и установка: docs/guides/grado-mcp.md.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.home()/'.grado2'/'agent')
    parser.add_argument('--port',type=int,default=8667)
    args=parser.parse_args()
    if not 1024<=args.port<=65535 or args.port==8650:
        parser.error('Нужен отдельный порт 1024–65535, кроме 8650')
    root=args.root.expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    token=root/'access-token'
    if not token.exists():
        fd=os.open(token,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(48))
    if token.stat().st_mode&0o077:
        raise SystemExit('Файл access-token должен быть доступен только владельцу (0600)')
    os.environ['GRADO2_PROJECTS']=str(root/'projects')
    os.environ['GRADO2_CACHE']=str(root/'cache')
    os.environ['GRADO2_TOKEN']=token.read_text().strip()
    os.environ['GRADO2_NO_BROWSER']='1'
    os.environ.pop('GRADO2_HUB',None)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps'/'grado2'))
    import server
    from portalgate import install_network_policy
    install_network_policy(server.CACHE)
    instance=server.Server(('127.0.0.1',args.port))
    try:instance.serve_forever()
    finally:instance.server_close()


if __name__=='__main__':main()
