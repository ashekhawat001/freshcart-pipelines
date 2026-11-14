import pika
import sys
import json

if len(sys.argv) < 3:
    print("Usage: python driver.py NAME PATTERN")
    sys.exit(1)

name = sys.argv[1]
pattern = sys.argv[2]

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
channel.exchange_declare(exchange='rapido-dispatch', exchange_type='topic')

result = channel.queue_declare(queue='', exclusive=True)
queue_name = result.method.queue
channel.queue_bind(exchange='rapido-dispatch', queue=queue_name, routing_key=pattern)

print(f"[*] Driver {name} listening on pattern '{pattern}'...", flush=True)

def callback(ch, method, properties, body):
    try:
        data = json.loads(body.decode())
        if 'zone' not in data:
            print(f"[{name}] REJECTED message {data.get('id')} - missing zone! (NACK, requeue=False)", flush=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        else:
            print(f"[{name}] PROCESSED message {data.get('id')} from zone {data['zone']}", flush=True)
            ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"[{name}] Error processing message: {e}", flush=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False)

try:
    channel.start_consuming()
except KeyboardInterrupt:
    pass
finally:
    connection.close()