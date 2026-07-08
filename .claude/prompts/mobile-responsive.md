Act as a Principal Lead Frontend Engineer, and Head of QA Automation. We are launching our MVP live to production in 2 to 3 days, and the vast majority of our merchants will access Modishlog entirely from mobile devices. Your primary objective is to execute a comprehensive, top-to-bottom mobile responsiveness and viewport alignment overhaul targeting the narrowest mobile screen standard: the iPhone SE (320px viewport width).

Critical Requirement: To accurately diagnose and fix layout bugs, you are authorized to use Playwright / Chromium headless browser utilities within this development environment to load pages, simulate an iPhone SE viewport width (320px), and visually inspect elements to ensure components are perfectly bound and centered.

Execute the following six-phase backlog systematically, self-testing and compiling your layout files after every single file modification to ensure zero build regressions.

---

## 📋 TASK MASTER EPIC: GLOBAL VIEWPORT, FORM HARDENING & VISUAL AUTOMATION PASS (IPHONE SE)

### PHASE 1: FORM & INTERACTIVE CARD STACKING ("ADD" ACTIONS ACCROSS ALL VIEWS)
Fix scattered and broken layouts inside input panels where forms are clipping or bleeding past their container cards on mobile views.
- **Form Row Flattening:** Target the 'Add Sale' page, 'Add Product' page, 'Add Customer' window, 'Add Supplier' modal, and 'Add Contact' forms across all application sections.
- **Grid-to-Row Restructuring:** Eliminate multi-column inline form layouts on mobile viewports. Force all text inputs, numerical fields, selection dropdowns, and text areas to stack cleanly in a single, vertical column (`flex flex-col` or `grid-cols-1`) so they stay strictly bounded within their containing cards.
- **Button Alignment:** Group modal confirm/cancel actions into full-width stacked rows or proportional block-level touch targets at the base of the card container.

---

### PHASE 2: FIXED SUB-TABS & ANCHORED VIEWPORT NAVIGATION (ALL SECTIONS)
Fix layout breakages across all inner tabs, sub-navigation components, and menu ribbons across every view in the app.
- **Top-Anchored Viewport Tabs:** For any section containing inner sub-tabs or contextual option switches, decouple the tab bar from the main page scroll flow. Anchor the tab container to the top of the mobile screen so it stays pinned within the active viewport.
- **Independent Horizontal Swipe Ribbons:** The tab bar itself must be independently horizontally scrollable (`overflow-x: auto; display: flex; flex-direction: row;订 whitespace-nowrap; scrollbar-none;`) across the top of the device. The tabs must NEVER bleed out of the right side of the screen or stretch the entire application layout horizontally.
- **Natural Body Scrolling:** Ensure that only the core table content or card feed below the pinned sub-tab bar scrolls vertically, preventing the navigation tabs themselves from scrolling out of view.

---

### PHASE 3: MARKETING LANDING PAGE SCREEN BOUNDS
Fix structural layout locks preventing standard navigation and gestures on smaller handheld glass screens.
- **Restore Mobile Scrolling:** Audit the landing page CSS structures, root layouts, and the homepage framework wrapper. Eliminate any hardcoded properties like `overflow: hidden`, `height: 100vh`, or absolute viewport pinning that are locking the vertical axes. Ensure smooth, natural touch scrolling (`overflow-y: auto`) across the entire screen depth.
- **Features & Pricing Flex Grid:** Convert multi-column grids in the "Features" and "Pricing" blocks into clean, single-column vertically stacked rows.
- **Popcorn Pricing Cards Adjustment:** Ensure each pricing block scales down perfectly to a 320px screen width with adequate margin and padding tokens so no borders or text labels cross outside the viewport edges.

---

### PHASE 4: BUSINESS DASHBOARD CARD MANAGEMENT
Transform sprawling grid structures into a predictable mobile card river.
- **Vertical Stack Overhaul:** Convert multi-column dashboard grid structures into strict single-item stacks (`grid-cols-1`). Every single metric container—including 'Today's Shop Summary', 'Your Clear Profit Today', 'Items Running Out', and financial overview blocks—must stack vertically on top of each other.
- **Card Content Proportionality:** Restrict data layouts inside the containers. Ensure typography scales down to prevent truncation. Text like large currency symbols and counts must wrap safely or fit cleanly within the card parameters without bleeding outside the viewport bounds.

---

### PHASE 5: NAVIGATION SWAPS & TACTILE ACCESSIBILITY (ALL SECTIONS)
- **Navigation Bar Switch:** Completely hide the 17-item desktop sidebar menu on devices under 768px wide. Replace it with a thumb-friendly sticky bottom navigation bar displaying the 4 core actions, or a responsive hamburger toggle drawer.
- **Form Controls Touch Zones:** Hard-enforce a minimum touch-target perimeter of 44x44px across all sub-tab choices, input blocks, checkboxes, and form buttons to optimize for high-speed POS use.

---

### PHASE 6: AUTOMATED HEADLESS CHECK & CLOSED VALIDATION LOOP
- **Chromium/Playwright Visual Audit:** Use Playwright or standalone Chromium execution scripts to render your layout changes under an iPhone SE profile. Programmatically confirm that no layouts yield a horizontal scroll property on the window root (`window.innerWidth` vs `document.documentElement.scrollWidth`).
- **Closed Pre-Flight Verification:** Execute these changes by modifying exactly one target file at a time. Immediately after every single update, trigger the local build sequence and validation suites (`npm run build`, lint checkers, and frontend test suites). Do not move to the next file until the current path compiles into production assets with a stable, zero-warning green status.