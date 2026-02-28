## ADDED Requirements

### Requirement: Parts library page with card grid
The application SHALL provide a `/library` page displaying all completed jobs as a card grid. Each card SHALL show: 3D thumbnail, part name, generation timestamp, and printability status badge.

#### Scenario: Library page displays jobs
- **WHEN** user navigates to the "零件库" tab
- **THEN** the application SHALL display a paginated card grid of all completed jobs, sorted by creation time descending

#### Scenario: Printability status badge
- **WHEN** a job has printability data
- **THEN** the card SHALL display a colored badge: green for "可打印", yellow for "需注意", red for "不可打印"

#### Scenario: Empty library
- **WHEN** no completed jobs exist
- **THEN** the page SHALL display an empty state with a prompt to start generating

### Requirement: Search and filter
The parts library SHALL support filtering by part type, printability status, and input type, plus full-text search on job names and descriptions.

#### Scenario: Filter by part type
- **WHEN** user selects "回转体" from the part type filter
- **THEN** only jobs with `part_type: "rotational"` SHALL be displayed

#### Scenario: Filter by printability
- **WHEN** user selects "需注意" from the status filter
- **THEN** only jobs with warnings in printability report SHALL be displayed

#### Scenario: Search by keyword
- **WHEN** user types "法兰" in the search box
- **THEN** jobs whose name or description contains "法兰" SHALL be displayed

#### Scenario: Combined filters
- **WHEN** user applies both part type and search filters
- **THEN** results SHALL satisfy ALL active filter conditions (AND logic)

### Requirement: Part detail view
Clicking a library card SHALL navigate to a detail view showing full 3D preview, DfAM report, generation parameters, and action buttons.

#### Scenario: Navigate to detail
- **WHEN** user clicks a job card in the library
- **THEN** the application SHALL navigate to `/library/:jobId` and display the detail view

#### Scenario: Detail view content
- **WHEN** detail view loads for a completed job
- **THEN** the view SHALL display: full 3D model viewer (center), DfAM printability report (right panel), generation parameters and metadata (left panel), and download/regenerate buttons

#### Scenario: Download from detail
- **WHEN** user clicks download in the detail view
- **THEN** the application SHALL offer format selection (STEP/GLB/STL/3MF based on pipeline type) and initiate download

### Requirement: Regenerate from library
Users SHALL be able to regenerate a part from the library, creating a new job with the same input parameters.

#### Scenario: Regenerate action
- **WHEN** user clicks "重新生成" on a part detail page
- **THEN** the application SHALL call `POST /api/v1/jobs/{id}/regenerate` and navigate to the appropriate workbench with the new job active

#### Scenario: Regenerate preserves parameters
- **WHEN** a regenerated job starts
- **THEN** the new job SHALL use the same `input_type`, `text`/`prompt`/`drawing`, and `template_params` as the original

### Requirement: Pagination
The parts library SHALL paginate results to maintain performance with large datasets.

#### Scenario: Default page size
- **WHEN** user opens the library without specifying page size
- **THEN** the library SHALL display 20 items per page

#### Scenario: Page navigation
- **WHEN** user clicks "下一页" or a specific page number
- **THEN** the library SHALL load and display the corresponding page of results
