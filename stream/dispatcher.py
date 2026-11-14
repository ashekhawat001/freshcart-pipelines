import pika
import json
import time
import random
import uuid

cities = ['bangalore', 'chennai']
zones = ['koramangala', 'indiranagar', 'whitefield', 'tnagar']
types = ['ride', 'food']

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
channel.exchange_declare(exchange='rapido-dispatch', exchange_type='topic')

print("Dispatcher started...")
message_count = 0
try:
    while True:
        message_count += 1
        city = random.choice(cities)
        zone = random.choice(zones)
        msg_type = random.choice(types)

        # Force Bangalore for bad messages so they are received by our active drivers
        if message_count % 10 == 0:
            city = 'bangalore'

        routing_key = f"{city}.{zone}.{msg_type}"
        payload = {
            "id": str(uuid.uuid4())[:8],
            "city": city,
            "type": msg_type,
            "ts": int(time.time())
        }

        # D3 Implementation: Omit "zone" on every 10th message
        if message_count % 10 != 0:
            payload["zone"] = zone
            print(f"[Dispatcher] Sent normal message #{message_count}: {routing_key}", flush=True)
        else:
            print(f"[Dispatcher] Sent BAD message #{message_count} (NO ZONE): {routing_key}", flush=True)

        channel.basic_publish(
            exchange='rapido-dispatch',
            routing_key=routing_key,
            body=json.dumps(payload)
        )
        time.sleep(1.5)
except KeyboardInterrupt:
    pass
finally:
    connection.close()
