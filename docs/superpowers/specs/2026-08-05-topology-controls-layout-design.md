# Topology Controls and Compact Layout Design

## Context

The topology page currently supports loading saved topology data and rediscovering every server. Its canvas and inspector use a large viewport-relative minimum height, so the bottom of the page can fall below the visible area. Operators also need a fast way to rediscover only the server selected in the topology inspector and a permanent explanation of what a discovered link means.

## Goals

- Allow rediscovery of only the currently selected server.
- Keep the single-server action in the inspector and hide it unless a server is selected.
- Explain every topology action with hover text instead of permanent button-description text.
- Permanently display the ARP/MAC-learning limitation above the canvas.
- Reduce the desktop canvas and inspector height so the complete topology work area fits in a normal viewport without page scrolling.
- Preserve the existing topology API and database format.

## User Interface

### Toolbar and explanations

The existing toolbar remains above the topology work area. Each action is wrapped in an Element Plus tooltip:

- `刷新拓扑`: `读取已有拓扑结果，不重新扫描设备`
- `重新生成拓扑图`: `扫描全部服务器并更新拓扑结果`
- `刷新当前服务器`: `仅扫描右侧当前选中的服务器`
- `重置视图`: `恢复画布的缩放比例和位置`

Only the ARP discovery explanation remains permanently visible. It appears as a compact, non-closable information alert between the toolbar and topology work area:

> 拓扑发现方式：服务器通过每个 UP 状态的网口发送 ARP 探测，再到已关联的交换机查询是否学习到该接口的 MAC 地址。因此，发现的链路不能保证两端为物理直连。

### Current-server refresh

The inspector header contains the existing `详情` action and a new `刷新当前服务器` action. The new action is rendered only when the selected node is a server. It is absent when a switch is selected or no node is selected.

While either full or single-server rediscovery is running, rediscovery actions are disabled to prevent overlapping requests. The active action shows a loading indicator. On success, the page reloads saved topology data and preserves the selected server when it still exists. Errors use the existing API error-message pattern and do not discard the existing graph.

## Data Flow

The frontend calls the existing `topology.discover(serverIds)` client:

- Full rediscovery passes no server list.
- Current-server rediscovery passes `[selectedNode.entity_id]`.

The backend already accepts `server_ids` at `POST /api/v1/topology/discover` and limits cleanup and discovery to those servers. No new route, database column, or migration is required.

## Layout

On desktop, the topology grid, canvas, and inspector share one bounded height:

```css
height: clamp(440px, calc(100dvh - 300px), 640px);
```

The canvas keeps its internal pan and zoom behavior. The inspector keeps its header and footer visible while its link-detail list scrolls internally when necessary. Existing viewport-relative minimum heights are removed so they cannot force the page below the fold.

Below the existing responsive breakpoint, the canvas and inspector continue stacking vertically. Mobile and unusually short viewports may scroll the page because preserving usable control and detail space takes priority over forcing both panels into one screen.

## Verification

- A UI source test first verifies the permanent ARP explanation, all four tooltip texts, and the server-only refresh action.
- A frontend behavior test or extracted helper test verifies that a selected server produces a discovery request containing exactly its ID and that switch selection does not expose the action.
- The production frontend build must pass.
- Manual browser verification checks tooltip visibility, server/switch conditional rendering, retained selection after refresh, internal inspector scrolling, and full desktop work-area visibility at common viewport heights.

## Out of Scope

- Changing how ARP discovery works.
- Adding switch-only rediscovery.
- Changing topology persistence or the database schema.
- Refactoring unrelated topology rendering or graph layout code.
