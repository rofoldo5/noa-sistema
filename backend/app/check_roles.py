"""Interactive CRUD smoke check against the API inside its container.

Creates one unassigned, uniquely named test role, updates it, removes it and
logs out its own session. It never reassigns people or changes existing roles.
"""
import getpass
import json
import secrets
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:8000'


def main():
    email = input('Correo SuperAdmin: ').strip()
    password = getpass.getpass('Contrasena (no se muestra ni se guarda): ')
    token = None
    code = 'QA_' + secrets.token_hex(4).upper()
    created = False
    failed = False

    def request(method, path, data=None, expected=200):
        payload = None if data is None else json.dumps(data).encode()
        headers = {'Content-Type':'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = Request(BASE+path, data=payload, headers=headers, method=method)
        try:
            response = urlopen(req, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            status = response.status
            raw = response.read()
        result = json.loads(raw) if raw else None
        if status != expected:
            detail = result.get('detail','') if isinstance(result,dict) else ''
            raise RuntimeError(f'{method} {path}: HTTP {status}. {detail}')
        return result

    try:
        result = request('POST','/auth/login',{'email':email,'password':password})
        token = result['access_token']
        password = None
        if result['user']['role'] != 'SUPERADMIN':
            raise RuntimeError('La cuenta no es SuperAdmin; no se creara ningun rol')
        request('GET','/admin/roles')
        print('OK: consulta de roles')
        role = request('POST','/admin/roles',{'code':code,'name':'Prueba '+code},expected=201)
        created = True
        print('OK: rol de prueba creado sin integrantes ni permisos adicionales')
        request('GET','/admin/roles/'+code)
        role = request('PATCH','/admin/roles/'+code,{'version':role['version'],'description':'Comprobacion CRUD temporal'})
        print('OK: consulta y modificacion')
        request('DELETE',f'/admin/roles/{code}?version={role["version"]}',expected=204)
        created = False
        request('GET','/admin/roles/'+code,expected=404)
        print('OK: eliminacion verificada; no se modificaron roles o usuarios existentes')
    except (RuntimeError, URLError, ValueError, KeyboardInterrupt) as exc:
        failed = True
        print(f'ERROR: {exc}', file=sys.stderr)
    finally:
        if token:
            if created:
                try:
                    role = request('GET','/admin/roles/'+code)
                    request('DELETE',f'/admin/roles/{code}?version={role["version"]}',expected=204)
                    print('OK: rol temporal retirado durante la limpieza')
                except Exception:
                    failed = True
                    print(f'ATENCION: revisar manualmente el rol temporal {code}; no se forzo su borrado',file=sys.stderr)
            try:
                request('POST','/auth/logout')
            except Exception:
                failed = True
                print('ATENCION: no se confirmo el cierre de la sesion de prueba',file=sys.stderr)
    if failed:
        raise SystemExit(1)
    print('CRUD comprobado. Las operaciones de prueba quedan registradas en auditoria.')


if __name__ == '__main__':
    main()
