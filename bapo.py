import asyncio
import websockets
import json
from random import randint

MAX_PLAYERS = 20
connected_clients = {}
batteries = []
battery_id_counter = 0
energy = 100
ENERGY_DECAY_RATE = 1
BATTERY_SPAWN_INTERVAL = 1
MAX_BATTERIES = 10
GAME_RESET_TIME = 10
INACTIVITY_TIMEOUT = 10

async def notify_all(message):
    if connected_clients:
        tasks = [client['websocket'].send(message) for client in connected_clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

async def spawn_batteries():
    global battery_id_counter
    while True:
        if len(batteries) < MAX_BATTERIES:
            battery_id_counter += 1
            new_battery = {
                'id': battery_id_counter,
                'x': randint(50, 750),
                'y': randint(50, 550)
            }
            batteries.append(new_battery)
            print(f"Nova bateria spawnada: {new_battery}")
            await notify_all(json.dumps({'type': 'battery_spawn', 'battery': new_battery}))
        await asyncio.sleep(BATTERY_SPAWN_INTERVAL)

async def decay_energy():
    global energy
    while True:
        await asyncio.sleep(1)
        energy -= ENERGY_DECAY_RATE
        if energy <= 0:
            energy = 0
            await notify_all(json.dumps({'type': 'update_energy', 'energy': energy}))
            await notify_all(json.dumps({'type': 'end_game'}))
            print("Energia acabou. Iniciando reinício do jogo...")
            await asyncio.sleep(GAME_RESET_TIME)
            await reset_game()
        else:
            await notify_all(json.dumps({'type': 'update_energy', 'energy': energy}))

async def reset_game():
    global energy, batteries, battery_id_counter
    energy = 100
    batteries.clear()
    battery_id_counter = 0
    print("Jogo resetado.")

    for client in connected_clients.values():
        player = client['player']
        player['x'] = randint(50, 750)
        player['y'] = randint(50, 550)
        player['direction'] = 'idle_right'
        player['carryingBattery'] = False

    game_state = {
        'type': 'game_reset',
        'players': [client['player'] for client in connected_clients.values()],
        'energy': energy,
        'batteries': batteries.copy()
    }
    await notify_all(json.dumps(game_state))

async def handler(websocket, path):
    global energy
    player_id = id(websocket)
    try:
        join_message = await websocket.recv()
        join_data = json.loads(join_message)
        if join_data.get('type') != 'join' or 'name' not in join_data:
            await websocket.send(json.dumps({'type': 'error', 'message': 'Mensagem de join inválida.'}))
            return

        player_name = join_data['name']
        if len(connected_clients) >= MAX_PLAYERS:
            await websocket.send(json.dumps({'type': 'wait', 'message': 'Servidor cheio. Aguardando espaço...'}))
            return

        player_hue = randint(0, 360)
        new_player = {
            'id': player_id,
            'name': player_name,
            'x': randint(50, 750),
            'y': randint(50, 550),
            'direction': 'idle_right',
            'hue': player_hue,
            'score': 0,
            'carryingBattery': False
        }
        connected_clients[player_id] = {'websocket': websocket, 'player': new_player}
        print(f"Jogador conectado: {new_player}")  # Log de depuração

        await websocket.send(json.dumps({'type': 'init', 'player': new_player}))
        await notify_all(json.dumps({'type': 'new_player', 'player': new_player}))
        for client in connected_clients.values():
            if client['player']['id'] != player_id:
                await websocket.send(json.dumps({'type': 'new_player', 'player': client['player']}))
        for battery in batteries:
            await websocket.send(json.dumps({'type': 'battery_spawn', 'battery': battery}))

        await websocket.send(json.dumps({'type': 'update_energy', 'energy': energy}))

        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=INACTIVITY_TIMEOUT)
                data = json.loads(message)
                if data.get('type') == 'move':
                    player = connected_clients[player_id]['player']
                    player['x'] = data.get('x', player['x'])
                    player['y'] = data.get('y', player['y'])
                    player['direction'] = data.get('direction', player['direction'])
                    player['carryingBattery'] = data.get('carryingBattery', player['carryingBattery'])
                    move_message = {'type': 'move', 'player': player}
                    await notify_all(json.dumps(move_message))
                elif data.get('type') == 'collect_battery':
                    battery_id = int(data.get('battery_id'))
                    player = connected_clients[player_id]['player']
                    print(f"Jogador {player['id']} ({player['name']}) está coletando a bateria {battery_id}")
                    for battery in batteries:
                        if battery['id'] == battery_id:
                            batteries.remove(battery)
                            player['carryingBattery'] = True
                            print(f"Bateria {battery_id} coletada por jogador {player['id']}")
                            await notify_all(json.dumps({
                                'type': 'battery_collected',
                                'batteryId': str(battery_id),
                                'collectedBy': player_id
                            }))
                            break
                elif data.get('type') == 'deliver_battery':
                    player = connected_clients[player_id]['player']
                    if player['carryingBattery']:
                        player['carryingBattery'] = False
                        player['score'] += 1
                        energy = min(100, energy + 1)
                        await notify_all(json.dumps({'type': 'update_energy', 'energy': energy}))
                        print(f"Jogador {player['id']} entregou uma bateria. Pontuação: {player['score']}")
            except asyncio.TimeoutError:
                try:
                    await websocket.send(json.dumps({'type': 'kick', 'message': 'Você foi desconectado por inatividade.'}))
                except:
                    pass
                await websocket.close()
                break

    except websockets.ConnectionClosed:
        print(f"Jogador {player_id} desconectado.")
        pass
    finally:
        if player_id in connected_clients:
            del connected_clients[player_id]
            await notify_all(json.dumps({'type': 'remove_player', 'id': player_id}))
            print(f"Jogador {player_id} removido da lista de conectados.")

async def main():
    server = await websockets.serve(handler, 'localhost', 8765)
    print("Servidor WebSocket iniciado na porta 8765")
    decay_task = asyncio.create_task(decay_energy())
    spawn_task = asyncio.create_task(spawn_batteries())
    try:
        await asyncio.Future()
    except KeyboardInterrupt:
        pass
    finally:
        decay_task.cancel()
        spawn_task.cancel()
        server.close()
        await server.wait_closed()
        print("Servidor WebSocket encerrado")

if __name__ == "__main__":
    asyncio.run(main())
