class ExecutionNotFoundError(Exception):
    def __init__(self, execution_id: str):
        super().__init__(f"Execution not found: execution_id={execution_id}")
        self.execution_id = execution_id
