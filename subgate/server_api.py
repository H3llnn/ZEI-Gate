"""Authenticated pull interface mounted on the existing HTTPS Mini App origin."""
from aiohttp import web


def routes(app, servers):
    @web.middleware
    async def errors(request, handler):
        try:
            return await handler(request)
        except PermissionError:
            return web.json_response({'error': 'Server tidak diizinkan.'}, status=403)
        except (ValueError, TypeError, KeyError, AttributeError):
            return web.json_response({'error': 'Permintaan server tidak valid.'}, status=400)

    async def enroll(request):
        body = await request.json()
        server = servers.enroll(body.get('code'), body.get('token'))
        return web.json_response({'server': server})

    async def sync(request):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            raise PermissionError
        body = await request.json()
        result = servers.heartbeat(auth[7:], body.get('report'),body.get('migration_version',0),body.get('migration_acks'))
        return web.json_response(result)

    async def migration(request):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer ') or not servers.migrations:
            raise PermissionError
        body = await request.json()
        action = body.get('action')
        role = 'source' if action in ('put','exported','cleaned','error_source') else 'target'
        service = servers.migrations
        async with service.lock:
            job = service.authorize(auth[7:], body['id'], role)
            if action == 'put':
                service.put(job,body['part'],body['data'])
            elif action == 'exported':
                service.exported(job,body['size'],body['digest'])
            elif action == 'get':
                part = body['part']
                if job['phase'] != 'import' or type(part) is not int or not 0 <= part < (job['size']+4499)//4500:
                    raise ValueError('Potongan tidak tersedia.')
                rows = service.db.rows('SELECT data FROM migration_chunks WHERE job=? AND part=?', (job['id'],part))
                import base64
                return web.json_response({'data':base64.b64encode(service.db.cipher.decrypt(rows[0]['data'])).decode()})
            elif action == 'installed':
                service.installed(job,body['receipt'])
            elif action == 'cleaned':
                service.cleaned(job)
            elif action in ('error_source','error_target'):
                with service.db.conn:
                    service.db.conn.execute("UPDATE migrations SET error='WorkerError' WHERE id=? AND phase!='done'", (job['id'],))
            else:
                raise ValueError('Aksi migrasi tidak tersedia.')
        return web.json_response({'ok':True})

    subapp = web.Application(client_max_size=2*1024*1024, middlewares=[errors])
    subapp.router.add_post('/enroll', enroll)
    subapp.router.add_post('/sync', sync)
    subapp.router.add_post('/migration', migration)
    app.add_subapp('/servers', subapp)
