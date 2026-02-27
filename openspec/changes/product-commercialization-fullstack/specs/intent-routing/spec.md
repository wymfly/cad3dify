## ADDED Requirements

### Requirement: LLM-driven intent parsing replaces keyword matching

The system SHALL use IntentParser (LLM-driven) as the primary method for routing user text input to parametric templates, replacing the current keyword matching (`_match_template()`).

#### Scenario: High confidence template match
- **WHEN** a user inputs "做一个直径 50mm 高 30mm 的法兰"
- **THEN** IntentParser returns IntentSpec with part_type=ROTATIONAL, known_params={outer_diameter: 50, height: 30}, confidence > 0.7
- **AND** the system routes to Track A (parametric template) with the matching template pre-selected

#### Scenario: Low confidence fallback to LLM generation
- **WHEN** IntentParser returns confidence < 0.7 or no matching template exists
- **THEN** the system routes to Track B (LLM code generation via V2 pipeline)

#### Scenario: IntentParser unavailable (LLM failure)
- **WHEN** the LLM call in IntentParser fails (timeout, API error, etc.)
- **THEN** the system automatically falls back to keyword matching (`_match_template()`)
- **AND** logs a warning about the fallback

### Requirement: Missing parameter identification

IntentParser SHALL identify which parameters are missing from the user's input relative to the matched template's required parameters.

#### Scenario: Partial parameters provided
- **WHEN** a user inputs "一个 L 型支架" (no dimensions specified)
- **THEN** IntentSpec.missing_params contains the template's required parameters (e.g., height, width, thickness, arm_length)
- **AND** the frontend prompts the user to fill in missing values via ParamForm

#### Scenario: All parameters provided
- **WHEN** a user inputs "直径 50mm 高 30mm 内孔 20mm 的法兰，8 个 M6 螺栓孔均布"
- **THEN** IntentSpec.missing_params is empty
- **AND** the system can proceed directly to generation (or HITL confirmation)

### Requirement: Part type mapping

IntentParser SHALL map Chinese part descriptions to PartType enum values, supporting common synonyms and variations.

#### Scenario: Chinese synonym resolution
- **WHEN** user input contains "法兰", "圆盘", or "盘"
- **THEN** IntentParser maps to PartType.ROTATIONAL
- **WHEN** user input contains "轴" or "阶梯轴"
- **THEN** IntentParser maps to PartType.ROTATIONAL_STEPPED
- **WHEN** user input contains "齿轮"
- **THEN** IntentParser maps to PartType.GEAR
