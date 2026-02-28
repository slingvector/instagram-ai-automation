# Backend Development Standards

This document outlines the standard practices and principles for backend development in the `streaming-prod` project.

## 1. SOLID Principles
We adhere to the SOLID principles to ensure our code is maintainable, scalable, and robust.

*   **S - Single Responsibility Principle (SRP):** Each class or module should have one, and only one, reason to change.
*   **O - Open/Closed Principle (OCP):** Software entities should be open for extension but closed for modification.
*   **L - Liskov Substitution Principle (LSP):** Subtypes must be substitutable for their base types.
*   **I - Interface Segregation Principle (ISP):** Clients should not be forced to depend on methods they do not use.
*   **D - Dependency Inversion Principle (DIP):** Depend on abstractions, not on concretions.

## 2. Separation of Concerns
We use a layered architecture to separate concerns:

*   **Controller Layer:** Handles HTTP requests and responses. Responsible for input validation and routing.
*   **Service Layer:** Contains the business logic. Orchestrates data flow and applies business rules.
*   **Repository Layer:** Handles data access and storage. Abstracts the database implementation.

## 3. Fault Tolerance & Error Handling
Systems must be designed to withstand failures.

*   **Graceful Degradation:** The system should continue to operate, possibly with reduced functionality, in the event of a failure.
*   **Retry Policies:** Implement intelligent retry mechanisms (e.g., exponential backoff) for transient failures.
*   **Circuit Breakers:** Prevent cascading failures by failing fast when a dependency is unhealthy.
*   **Structured Logging:** Use structured logs (JSON) with correlation IDs to trace requests across services.
*   **Centralized Error Handling:** Use global exception handlers to return consistent error responses to clients.

## 4. Portability & Determinism
"It runs on my machine" is not an acceptable excuse.

*   **Containerization:** Use Docker for all services to ensure consistent environments across development, testing, and production.
*   **Configuration Management:** Store configuration in environment variables, not code.
*   **Reproducible Builds:** Use lock files (e.g., `package-lock.json`, `go.sum`) to ensure dependency consistency.

## 5. Modularity & Extensibility
*   **Code Organization:** Group code by feature or domain, not just technical layer.
*   **Interfaces:** Define clear interfaces between modules to allow implementation changes without affecting consumers.

## 6. High Availability & Observability
*   **Health Checks:** Expose health check endpoints (liveness and readiness probes).
*   **Metrics:** Instrument code to emit standard metrics (latency, throughput, error rate).
*   **Tracing:** Implement distributed tracing (e.g., OpenTelemetry) to visualize request flows.

## 7. Testing
*   **Unit Tests:** Test individual components in isolation. Mock dependencies.
*   **Integration Tests:** Verify interactions between components (e.g., service and database).
*   **E2E Tests:** Validate critical user flows from start to finish.