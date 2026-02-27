## ADDED Requirements

### Requirement: Automatic printability check after generation

The system SHALL automatically run PrintabilityChecker after every successful model generation (both precision modeling and organic paths), producing a PrintabilityResult containing pass/fail status, individual issue diagnostics, and material/cost estimates.

#### Scenario: Precision modeling generation triggers check
- **WHEN** a precision modeling job completes successfully with a STEP file output
- **THEN** the system extracts geometry_info from the STEP file and runs PrintabilityChecker.check() + estimate_material() + estimate_print_time() with the user's selected print profile (defaulting to FDM Standard)
- **AND** the SSE `completed` event includes a `printability` field with the full PrintabilityResult including material_estimate (weight, length, cost) and time_estimate (total minutes, layer count)

#### Scenario: Organic path generation triggers check
- **WHEN** an organic path job completes successfully with mesh output
- **THEN** the system extracts geometry_info from the mesh (vertex count, bounding box, watertight status, estimated wall thickness) and runs PrintabilityChecker
- **AND** the SSE `completed` event includes a `printability` field

#### Scenario: Check failure does not block generation result
- **WHEN** PrintabilityChecker raises an exception during analysis
- **THEN** the generation result is still returned successfully
- **AND** the `printability` field is null with a warning message explaining the check failure

### Requirement: Geometry information extraction

The system SHALL provide a geometry extractor that produces a standardized `geometry_info` dict from either STEP files (via OCP/CadQuery geometric queries) or mesh files (via trimesh analysis).

#### Scenario: Extract from STEP file
- **WHEN** given a valid STEP file path
- **THEN** the extractor returns `geometry_info` containing: bounding_box (x/y/z mm), min_wall_thickness (mm), max_overhang_angle (degrees), volume_cm3, and min_hole_diameter (mm)

#### Scenario: Extract from mesh file
- **WHEN** given a valid GLB/STL mesh file path
- **THEN** the extractor returns `geometry_info` with the same fields, using trimesh-based approximations for overhang analysis
- **AND** min_wall_thickness may be None for mesh files (computationally expensive, optional)

### Requirement: Frontend PrintReport rendering

The system SHALL render the PrintabilityResult in the frontend result card, showing pass/fail status, individual check results with severity indicators, and material cost estimate.

#### Scenario: All checks pass
- **WHEN** PrintabilityResult.printable is true with zero issues
- **THEN** the PrintReport component displays a green "可打印" badge and the material/cost summary

#### Scenario: Issues detected
- **WHEN** PrintabilityResult contains one or more issues (wall thickness too thin, overhang too steep, etc.)
- **THEN** each issue is displayed with severity (error/warning), affected dimension value, and the threshold it violates
- **AND** a correction suggestion is shown for each issue
