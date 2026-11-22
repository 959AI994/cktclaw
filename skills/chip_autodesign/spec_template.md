# AutoDesign Spec Template

## Goal
State the user-visible purpose of the IP and the exact behavior to implement.

## Interface
List every port or bus channel, direction, width, and protocol meaning.

## Clock and Reset
Declare clock domains, reset polarity, reset behavior, and assumptions.

## Parameters and Widths
Record configurable parameters and default values.

## Verification Requirements
Include directed functional tests, boundary tests, protocol tests, and any
negative cases needed to expose likely bugs.

## PPA Targets
Use correctness-first defaults unless the user provides area, timing, or power
constraints. Generic Yosys cell counts are proxy QoR only.

## Non-Goals
Explicitly exclude unsupported scope such as full SoC integration, physical
design, or power/timing signoff when those flows are not attached.
