import asyncio
from app.knowledge.openviking import OpenVikingClient

async def test():
    ov = OpenVikingClient('http://localhost:1933', 'test-debug')
    await ov.start()

    r1 = await ov.mkdir('viking://resources/hdc/debug_test', 'test')
    print(f'mkdir: {r1}')

    r2 = await ov.write('viking://resources/hdc/debug_test/test.md', '# test',
mode='create')
    print(f'write(create): {r2}')

    r3 = await ov.set_tags('viking://resources/hdc/debug_test', ['test=hello'],
mode='replace')
    print(f'set_tags: {r3}')

    await ov.close()

asyncio.run(test())