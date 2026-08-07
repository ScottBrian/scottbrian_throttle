import time


class MultiEngineProcessor:
    @track_state(initial_status="ready", increment_by=5)
    def sync_task(self):
        time.sleep(0.01)
        return "sync done"

    @track_state(initial_status="ready_async", increment_by=1)
    async def async_task(self):
        await asyncio.sleep(0.01)
        return "async done"


# ----------------- Execution & Test Verification -----------------
async def main():
    engine = MultiEngineProcessor()

    # Test 1: Verify Standard Sync Tracking
    engine.sync_task()
    print(f"Sync Counter: {engine.sync_task.count} | Status: {engine.sync_task.status}")
    # Output: Sync Counter: 5 | Status: success

    # Test 2: Verify Proper Async Interception and Tracking
    await engine.async_task()
    print(
        f"Async Counter: {engine.async_task.count} | Status: {engine.async_task.status}"
    )
    # Output: Async Counter: 1 | Status: success

    # Test 3: Verify the Automatic Teardown Routine Context Manager
    print(f"\nStatus before error: {engine.sync_task.status}")
    try:
        with engine.sync_task.teardown_context():
            print("Executing critical segment... forcing simulation error.")
            raise ValueError("Something crashed!")
    except ValueError:
        print("Caught simulation error outside.")

    print(f"Status after teardown: {engine.sync_task.status}")
    print(f"Log history: {engine.sync_task.history[-1]}")


# Run the async loop validation
asyncio.run(main())


###################################################
# latest
####################################################
"""

Practical Verification Example
Below, we define a custom failure alert function and assign it to an active worker class to intercept runtime exceptions.
"""


# 1. Define global or class-level callback handlers
def global_alert_system(instance, proxy, exception):
    """Custom sync callback triggered immediately when any tracked method fails."""
    print(f"\n[ALERT] Incident detected on object: {instance}")
    print(f"[ALERT] Method Status: {proxy.status}")
    print(f"[ALERT] Total invocation attempts before failure: {proxy.count}")
    print(f"[ALERT] Exception Type: {type(exception).__name__} | Message: {exception}")


async def async_logging_system(instance, proxy):
    """Custom async callback triggered upon a successful method execution."""
    await asyncio.sleep(0.001)  # Simulate non-blocking async network log write
    print(
        f"\n[LOG] Success confirmation logged for {instance}. Execution count: {proxy.count}"
    )


# 2. Build the class applying our callbacks directly into the decorator
class DataIngestionEngine:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"DataIngestionEngine({self.name})"

    @track_state(on_success=async_logging_system, on_failure=global_alert_system)
    def process_records(self, should_fail=False):
        if should_fail:
            raise ConnectionResetError(
                "Remote server closed the streaming socket abruptly."
            )
        return "Records processed successfully."


# 3. Execute the pipeline simulation
def run_test():
    engine_1 = DataIngestionEngine("Primary_Cluster")

    # Test Case A: Success Path
    print("--- Running Success Path ---")
    engine_1.process_records(should_fail=False)

    # Test Case B: Failure Path with Auto-Callback Trigger
    print("\n--- Running Failure Path ---")
    try:
        engine_1.process_records(should_fail=True)
    except ConnectionResetError:
        print(
            "\n[Main Thread] Caught the expected exception bubbles-up from the class method."
        )


run_test()


"""
Key Highlights of this ArchitectureContext Preservation: 
The helper _execute_callback receives both instance (the actual class instance, e.g., self) and proxy (the method state object). 
This allows your callbacks to access internal object attributes or verify metrics like proxy.count directly.
Smart Event-Loop Routing: If a user provides an async def callback to a synchronous tracking path,
 the engine leverages asyncio.get_running_loop().create_task() to schedule it on the loop without freezing the
  thread or throwing a RuntimeError.State Retention: In addition to setting proxy.status = 'failed', 
  the proxy retains the actual Python exception object under proxy.last_exception, letting you inspect traceback details after the fact.
"""
