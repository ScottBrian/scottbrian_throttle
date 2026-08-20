import asyncio
import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from scottbrian_throttle.throttle_blocks import hybrid_delayed_execution

# 1. Hook up OpenTelemetry to our local Docker Jaeger container
resource = Resource(attributes={"service.name": "payment-gateway-service"})
provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
)
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("main_app")


# 2. Decorate a working function and a failing function
@hybrid_delayed_execution(delay=0.5, sync_action="convert_to_async")
def successful_third_party_calc():
    time.sleep(0.2)
    return "Calculated Data"


@hybrid_delayed_execution(delay=0.5, sync_action="convert_to_async")
def failing_third_party_calc():
    time.sleep(0.1)
    raise ConnectionResetError("Remote server abruptly closed connection!")


# 3. Main runtime loop
async def main():
    # ---- TRANSACTION 1: Success ----
    with tracer.start_as_current_span("HTTP POST /process-payment"):
        print("Running successful transaction...")
        await successful_third_party_calc()

    # ---- TRANSACTION 2: Error ----
    with tracer.start_as_current_span("HTTP POST /refund-payment"):
        print("Running failing transaction...")
        try:
            await failing_third_party_calc()
        except ConnectionResetError:
            print("Caught exception safely in main app logic!")


if __name__ == "__main__":
    asyncio.run(main())
    provider.shutdown()  # Force push remaining trace blocks before exit
