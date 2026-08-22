# Temporary authoritative compiler bridge V1

These fixtures are frozen transcriptions from the currently unavailable
DemandRegime + TripAllocator source machine.  Their upstream hashes are
provenance assertions; this repository does not claim to reproduce them.

The production compiler consumes only `CompilerInputV1`.  It does not import
or inspect these JSON fixtures.

## TODO: real allocator integration gate

When the original allocator branch is available:

1. load the real `TripAllocationCandidate`;
2. convert it through `RealTripAllocatorAdapter`;
3. serialize the resulting `CompilerInputV1`;
4. compare it byte-for-byte with this bridge's neutral compiler input;
5. run the compiler only after equality is proven;
6. require byte-identical compiled output.

The bridge can then be retired without modifying the compiler algorithm.
