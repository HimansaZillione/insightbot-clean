Here's the full summary of what we have:

---

## Repository: `insightbot-clean`

**Default branch: `main`**

| Branch | Tag | Description | Use |
|---|---|---|---|
| `main` | `v1.0-single-container-ui-changes` | Initial push | — |
| `main` | `v1.1-single-container-ui-changes-fixed-2.1.0` | Single container + UI changes + azure-ai-projects 2.1.0 fixes | ✅ Client tenant production |
| `feature/dual-container-ui-changes` | `v1.2-dual-container-ui-changes-fixed-2.1.0` | Dual container + UI changes + azure-ai-projects 2.1.0 fixes | ✅ Internal use |
| `feature/internal-dual-container-no-ui-changes` | `v1.3-internal-dual-container-no-ui-changes` | Dual container + reverted UI to Fluent default + citation & image rendering preserved | ✅ Internal use |

---

## What each version contains

**`main` / `v1.1`:**
- Single blob container logic in `routes.py`
- UI changes — image rendering in `AssistantMessage.tsx`
- `azure-ai-projects==2.1.0` fixes
- `SEARCH_CONNECTION_ID` for client tenant

**`feature/dual-container-ui-changes` / `v1.2`:**
- Dual blob container logic in `routes.py`
- UI changes — image rendering in `AssistantMessage.tsx`
- `azure-ai-projects==2.1.0` fixes
- `SEARCH_CONNECTION_ID` for internal/SLIIT tenant

**`feature/internal-dual-container-no-ui-changes` / `v1.3`:**
- Dual blob container logic in `routes.py`
- UI reverted to default Fluent UI theme (no custom dark styling)
- Citation rendering preserved — deduplication, SAS proxy links, fallback text
- Code interpreter image rendering preserved in `AssistantMessage.tsx`
- `AgentPreview.tsx` — strips "for SLIIT" from agent name display, Contact/About us match New Chat button style
- `azure-ai-projects==2.1.0` fixes
- `SEARCH_CONNECTION_ID` for internal/SLIIT tenant

---

## Key fixes applied to both branches
- `AgentVersionObject` → `AgentVersionDetails`
- `AzureAISearchAgentTool` → `AzureAISearchTool`
- `CodeInterpreterContainerAuto` → `AutoCodeInterpreterToolParam`
- `AgentReference` removed → plain dict with `agent_reference`
- File status `completed` → `processed`
- `azure-core==1.36.0` → `azure-core>=1.37.0`
- `extra_body["agent"]` → `extra_body["agent_reference"]`

-----------------------------------------------------------------------------------------------------
#To Pull a specific version 
------------------------------------------------------------------------------------------------------
Simple — just use the tag:

```powershell
# Pull a specific version by tag
git checkout v1.1-single-container-ui-changes-fixed-2.1.0

# Or pull the dual container version
git checkout v1.2-dual-container-ui-changes-fixed-2.1.0
```

Or by branch:

```powershell
# Pull client version
git checkout main

# Pull internal version
git checkout feature/dual-container-ui-changes
```

**To get a fresh copy on a new machine:**

```powershell
# Clone the repo
git clone https://github.com/HimansaZillione/insightbot-clean.git

# Then checkout the version you want
cd insightbot-clean
git checkout v1.1-single-container-ui-changes-fixed-2.1.0
```

**To see all available tags and branches:**

```powershell
# List all tags
git tag

# List all branches
git branch -a

# See tags with descriptions
git tag -n
```

The tag approach is the most reliable — it's a fixed snapshot that never changes regardless of future commits to the branch.