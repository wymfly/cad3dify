## ADDED Requirements

### Requirement: PaddleOCR engine integration

The system SHALL integrate PaddleOCR as the OCR engine for extracting text regions from engineering drawings, wrapped in the existing `ocr_fn: Callable` interface of OCRAssistant.

#### Scenario: OCR extraction from drawing image
- **WHEN** an engineering drawing image is provided to the OCR engine
- **THEN** PaddleOCR extracts all text regions with bounding box coordinates, recognized text, and confidence scores
- **AND** results are returned as a list of OCRResult objects

#### Scenario: PaddleOCR not installed
- **WHEN** PaddleOCR package is not installed (optional dependency)
- **THEN** the system logs a warning and falls back to VLM-only mode (no OCR fusion)
- **AND** generation proceeds normally without OCR enhancement

### Requirement: OCR-VLM fusion in drawing pipeline

The system SHALL merge OCR-extracted dimensions with VLM-extracted semantic information using the existing `merge_ocr_with_vl()` function, integrated into the DrawingAnalyzer pipeline.

#### Scenario: Successful fusion
- **WHEN** both OCR and VLM produce dimension results for the same drawing
- **THEN** numeric fields (diameters, lengths, tolerances) use OCR values (higher precision for `φ50`, `R15`, `50±0.1` patterns)
- **AND** semantic fields (part type, feature descriptions) use VLM values (better contextual understanding)
- **AND** the merged DrawingSpec includes a confidence score for each field

#### Scenario: OCR finds dimensions VLM missed
- **WHEN** OCR detects a dimension annotation (e.g., `6×M8`) that VLM did not extract
- **THEN** the OCR-found dimension is added to the DrawingSpec with a flag indicating it was OCR-sourced

#### Scenario: OCR and VLM disagree on a value
- **WHEN** OCR reads a dimension as 50mm but VLM reads it as 55mm
- **THEN** the system uses the OCR value (higher precision for numeric data)
- **AND** records the disagreement in the DrawingSpec confidence metadata

### Requirement: Dimension pattern recognition

The OCR dimension parser SHALL recognize standard engineering drawing annotation patterns including diameter (φD), radius (R), count×diameter (N×φD), tolerances (N±T), and thread specifications (M×pitch).

#### Scenario: Standard dimension patterns
- **WHEN** OCR text contains "φ50", "R15", "6×φ10", "50±0.1", or "M8×1.25"
- **THEN** each is correctly parsed into structured DimensionAnnotation with type, value, and unit

#### Scenario: Noise filtering
- **WHEN** OCR text contains surface roughness annotations (Ra, Rz) or material callouts
- **THEN** these are filtered out and not included in the dimension results
