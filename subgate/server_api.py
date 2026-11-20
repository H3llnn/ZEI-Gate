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
        result = servers.heartbeat(auth[7:], body.get('report'))
        return web.json_response(result)

    subapp = web.Application(client_max_size=2*1024*1024, middlewares=[errors])
    subapp.router.add_post('/enroll', enroll)
    subapp.router.add_post('/sync', sync)
    app.add_subapp('/servers', subapp)
