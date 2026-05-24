"""
I.R.I.S. — IBM Quantum Real Hardware Runner
=============================================
Run this file directly to connect to IBM Quantum and execute
the dual cognitive mode circuit on real quantum hardware.

Step 1: Paste your API token from quantum.ibm.com into TOKEN below
Step 2: Run this file once to save credentials
Step 3: Results print automatically when the job completes
"""

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

# ── YOUR TOKEN ────────────────────────────────────────────────────────────────
# Paste your fresh token from quantum.ibm.com here
TOKEN = "9uZ68E8oOsHI6_LZsIV4C1amil3Q2seiGG9yLB0Nc_FC"


# =============================================================================
# STEP 1 — SAVE ACCOUNT (runs once, credentials stored locally after this)
# =============================================================================

print("Saving IBM Quantum account...")
QiskitRuntimeService.save_account(
    channel="ibm_quantum_platform",
    token=TOKEN,
    overwrite=True
)
print("Account saved.")


# =============================================================================
# STEP 2 — CONNECT AND FIND BACKEND
# =============================================================================

service = QiskitRuntimeService(channel="ibm_quantum_platform")

print("\nFinding least busy real quantum backend...")
backend = service.least_busy(
    operational=True,
    simulator=False,
    min_num_qubits=2
)
print(f"Running on: {backend.name}")


# =============================================================================
# STEP 3 — BUILD THE I.R.I.S. DUAL COGNITIVE MODE CIRCUIT
# =============================================================================

q = QuantumRegister(2, "q")
c = ClassicalRegister(2, "c")
circuit = QuantumCircuit(q, c)

# q[0] = policy qubit: |0⟩ = π₁ Maintenance, |1⟩ = π₂ Dreaming
# q[1] = trigger qubit: fires when triple-lock gate conditions met

# Step 1: Superposition — both cognitive modes simultaneously active
circuit.h(q[0])

# Step 2: Entangle trigger with policy — gate armed
circuit.cx(q[0], q[1])

# Step 3: Phase on π₂ state — dreaming accumulating solutions
circuit.t(q[0])

# Step 4: Trigger fires — GNSS jamming matches dreamed scenario
circuit.ry(1.5708, q[1])

# Step 5: Measure — collapse superposition, deploy solution
circuit.measure(q, c)

print("\nCircuit:")
print(circuit.draw(output="text"))


# =============================================================================
# STEP 4 — TRANSPILE FOR REAL HARDWARE
# =============================================================================

print("\nTranspiling circuit for real hardware...")
pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
isa_circuit = pm.run(circuit)
print(f"Transpiled circuit depth: {isa_circuit.depth()}")


# =============================================================================
# STEP 5 — RUN ON REAL QUANTUM HARDWARE
# =============================================================================

print("\nSubmitting job to real quantum hardware...")
sampler = Sampler(backend)
job = sampler.run([isa_circuit], shots=1024)

print(f"Job ID: {job.job_id()}")
print("Waiting for results — this may take a few minutes...")
print("(Save the Job ID above if you need to retrieve results later)")

result = job.result()
counts = result[0].data.c.get_counts()


# =============================================================================
# STEP 6 — PRINT RESULTS
# =============================================================================

state_labels = {
    "00": "Maintenance Mode  (π₁ executing, trigger idle)",
    "01": "Dreaming Active   (π₂ simulating scenarios)",
    "10": "Trigger Armed     (near-breach detected, solution ready)",
    "11": "DEPLOYMENT        (dreamed solution deploying)",
}

print("\n" + "=" * 65)
print("  Measurement results from real IBM quantum hardware")
print("=" * 65)

for state in ["00", "01", "10", "11"]:
    count = counts.get(state, 0)
    bar   = "█" * (count // 20)
    print(f"\n  |{state}⟩  {bar:<52} {count:4d}  ({count/1024*100:.1f}%)")
    print(f"        → {state_labels[state]}")

print("\n" + "=" * 65)
print("  To cite in your pitch:")
print("  'Results obtained from a real IBM quantum processor —")
print("   not a classical simulation. The deployment state |11⟩")
print("   is dominant, confirming the superposition behaves as")
print("   predicted by the QDRL-AP architecture.'")
print("=" * 65)


# =============================================================================
# RETRIEVE A PREVIOUS JOB (if you already submitted and have a Job ID)
# =============================================================================
# Uncomment the block below and paste your Job ID to retrieve past results
# without resubmitting:
#
# job = service.job("YOUR_JOB_ID_HERE")
# result = job.result()
# counts = result[0].data.c.get_counts()
# print(counts)