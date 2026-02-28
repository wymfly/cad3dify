## ADDED Requirements

### Requirement: Three-panel workbench layout
The application SHALL use a three-panel layout: left panel (240px, collapsible), center 3D preview (flex:1), right panel (300px, collapsible).

#### Scenario: Default layout
- **WHEN** user opens the precision or organic workbench
- **THEN** all three panels SHALL be visible with the center panel occupying remaining horizontal space

#### Scenario: Panel collapse
- **WHEN** user clicks the collapse button on left or right panel
- **THEN** the panel SHALL collapse and the center area SHALL expand to fill the space

#### Scenario: Collapse state persistence
- **WHEN** user collapses a panel and refreshes the page
- **THEN** the panel SHALL remain collapsed (state persisted in localStorage)

#### Scenario: Small screen adaptation
- **WHEN** viewport width is below 768px
- **THEN** left and right panels SHALL transform into bottom drawers instead of side panels

### Requirement: Top tab navigation
The application SHALL use a top navigation bar with tabs for "精密建模", "创意雕塑", and "零件库". The sidebar menu SHALL be replaced entirely.

#### Scenario: Tab switching
- **WHEN** user clicks the "创意雕塑" tab
- **THEN** the application SHALL navigate to `/organic` and display the organic workbench

#### Scenario: Active tab indicator
- **WHEN** user is on `/precision`
- **THEN** the "精密建模" tab SHALL be visually highlighted as active

### Requirement: Light/dark theme switching
The application SHALL support light and dark themes via Ant Design 6 ConfigProvider algorithm switching.

#### Scenario: Default theme
- **WHEN** user opens the application for the first time
- **THEN** the light theme SHALL be applied by default

#### Scenario: Toggle theme
- **WHEN** user clicks the theme toggle button (☀/☾) in the top navigation bar
- **THEN** the theme SHALL switch between light and dark modes immediately

#### Scenario: Theme persistence
- **WHEN** user selects dark mode and refreshes the page
- **THEN** dark mode SHALL be preserved (stored in localStorage)

#### Scenario: 3D viewer theme sync
- **WHEN** dark mode is active
- **THEN** the 3D preview background SHALL change to `#0a0a0a` and ambient light SHALL be reduced

### Requirement: Left panel auto-switching by pipeline stage
The left panel content SHALL automatically switch based on the current pipeline stage. Users SHALL NOT need to manually navigate between stages.

#### Scenario: Idle state shows input panel
- **WHEN** no job is active
- **THEN** left panel SHALL display the InputPanel (text input + drawing upload + template selection)

#### Scenario: HITL drawing confirmation
- **WHEN** pipeline reaches `awaiting_confirmation` with a DrawingSpec
- **THEN** left panel SHALL switch to DrawingSpecForm (editable structured form)

#### Scenario: HITL parameter confirmation
- **WHEN** pipeline reaches `awaiting_confirmation` with template parameters
- **THEN** left panel SHALL switch to ParamForm (sliders + inputs + recommendations)

#### Scenario: Generation in progress
- **WHEN** pipeline is in `generating` or `refining` status
- **THEN** left panel SHALL switch to PipelineProgress (stage status + elapsed time)

#### Scenario: Completed
- **WHEN** pipeline reaches `completed` status
- **THEN** left panel SHALL switch to DownloadPanel (format selection + save to library)

### Requirement: Right panel contextual content
The right panel SHALL display contextual information based on the current pipeline stage.

#### Scenario: Idle state shows recommendations
- **WHEN** no job is active
- **THEN** right panel SHALL display template recommendations and recent generation history

#### Scenario: Drawing confirmation shows original image
- **WHEN** left panel shows DrawingSpecForm
- **THEN** right panel SHALL display the original uploaded drawing image for comparison

#### Scenario: Generation shows pipeline log
- **WHEN** pipeline is actively generating
- **THEN** right panel SHALL display PipelineLog with real-time SSE events

#### Scenario: Completed shows DfAM report
- **WHEN** pipeline is completed
- **THEN** right panel SHALL display PrintReport with printability results, material costs, and time estimates

### Requirement: Step-by-step wizard interaction
The workbench SHALL guide users through the workflow with clear visual progression. Users SHALL always know what step they are on and what comes next.

#### Scenario: Pipeline progress display
- **WHEN** pipeline is active
- **THEN** PipelineProgress SHALL display all stages with their status (pending/running/success/failed) and elapsed time

#### Scenario: Clear call-to-action
- **WHEN** HITL confirmation is required
- **THEN** the left panel SHALL prominently display "确认并生成" button at the bottom
