# Phase 8 — Admin Panel UI (Document Upload + Management)

## Concepts Learned

### expo-document-picker
`expo-document-picker` wraps the native file pickers:
- iOS: `UIDocumentPicker`
- Android: Android Storage Access Framework (SAF)

API (v54+):
```typescript
import * as DocumentPicker from 'expo-document-picker';

const result = await DocumentPicker.getDocumentAsync({
  type: ['application/pdf', ...],
  copyToCacheDirectory: true,
  multiple: false,
});

if (!result.canceled && result.assets?.length) {
  const { uri, name, mimeType, size } = result.assets[0];
}
```

### FormData for multipart/form-data upload
HTTP file uploads use `multipart/form-data` encoding. We create a `FormData`
object and attach the file with its `uri`, `name`, and `type`. React Native's
HTTP stack (backed by the native HTTP client) encodes this correctly for the
`Content-Type: multipart/form-data` request.

```typescript
const formData = new FormData();
formData.append('department', department);
formData.append('file', { uri, name, type: mimeType } as unknown as Blob);

await axios.post('/admin/documents/upload', formData, {
  headers: { 'Content-Type': 'multipart/form-data' },
  onUploadProgress: (e) => setProgress(Math.round(e.loaded * 100 / e.total)),
});
```

### Upload Progress with Axios
`onUploadProgress` fires repeatedly as the request body is sent. We use it to
drive a simple progress bar. This requires a `Content-Length` header — Axios
sets it automatically when the FormData size is known.

### Role-Based Navigation
Admin users get a `BottomTabNavigator` with two tabs:
- **Chats tab** → `ChatStack` (Home → Chat) — same as regular users
- **Admin tab** → `AdminStack` (AdminHome → DocumentList → UploadDocument)

Regular users get only `ChatNavigator` (no tab bar). The `Root` component
checks `user.role` at render time and returns the appropriate navigator.

```typescript
function Root() {
  const { user, isLoading } = useAuth();
  if (!user) return <AuthNavigator />;
  if (user.role === 'admin') return <AdminTabNavigator />;
  return <ChatNavigator />;
}
```

### Nested Navigators
The bottom tab navigator contains two nested stack navigators. Each stack
maintains its own history independently — back navigation in the Admin tab
doesn't affect the Chats tab.

### Destructive Actions with Alert.alert
`Alert.alert()` is the idiomatic React Native way to show a confirmation
dialog before irreversible actions. It uses native UI on both platforms:
- iOS: `UIAlertController`
- Android: `AlertDialog`

```typescript
Alert.alert('Delete Document', 'Remove "policy.pdf"?', [
  { text: 'Cancel',  style: 'cancel' },
  { text: 'Delete',  style: 'destructive', onPress: doDelete },
]);
```

### 202 Accepted + polling pattern
The backend ingestion pipeline (parse→chunk→embed→FAISS) can take 5–30 seconds.
The upload endpoint returns `202 Accepted` immediately; the actual indexing
runs as a background task. The UI shows a "check the document list" message
and the admin can pull-to-refresh to see when chunks appear.

---

## What Was Built

### `mobile/services/api.ts` (updated)
Added `DocumentInfo` interface and `adminApi` object:
```typescript
export const adminApi = {
  listDocuments:  (department?) => api.get<DocumentInfo[]>('/admin/documents', ...),
  getDocument:    (id) => api.get<DocumentInfo>(`/admin/documents/${id}`),
  deleteDocument: (id) => api.delete(`/admin/documents/${id}`),
  uploadDocument: (formData, onProgress?) => api.post('/admin/documents/upload', ...),
};
```

### `mobile/screens/admin/AdminHomeScreen.tsx`
- Fetches all documents once and groups by department client-side (one API call)
- Shows each department as a card with document count badge
- Pull-to-refresh with `RefreshControl`
- Tapping a card navigates to `DocumentList` for that department

### `mobile/screens/admin/DocumentListScreen.tsx`
- Lists all documents for a department with type emoji, chunk count, upload date
- Delete button per row → `Alert.alert` confirmation → optimistic UI removal
- `ActivityIndicator` per row while deletion is in progress
- Floating "Upload" button navigates to `UploadDocument`
- Pull-to-refresh

### `mobile/screens/admin/UploadDocumentScreen.tsx`
- Tap-to-open native file picker (expo-document-picker)
- Shows selected file name and size
- FormData upload with Axios progress callbacks driving a native progress bar
- Success state with "back to list" + "upload another" actions
- Error state displays the backend's `detail` message

### `mobile/App.tsx` (updated)
- `AdminStackParamList` type added for the admin screen stack
- `AdminTabParamList` type for the two tab names
- `ChatNavigator()` — stack with Home + Chat (used by regular users and as a tab)
- `AdminNavigator()` — stack with AdminHome + DocumentList + UploadDocument
- `AdminTabNavigator()` — bottom tabs wrapping both navigators with emoji icons
- `Root()` now branches on `user.role`:
  - `null` → `AuthNavigator`
  - `'admin'` → `AdminTabNavigator`
  - `'user'` → `ChatNavigator`

---

## File Checklist

| File | Status |
|---|---|
| `mobile/services/api.ts` | ✅ Updated — adminApi + DocumentInfo |
| `mobile/screens/admin/AdminHomeScreen.tsx` | ✅ New |
| `mobile/screens/admin/DocumentListScreen.tsx` | ✅ New |
| `mobile/screens/admin/UploadDocumentScreen.tsx` | ✅ New |
| `mobile/App.tsx` | ✅ Updated — bottom tab + admin navigator |

**TypeScript:** `npx tsc --noEmit` → 0 errors.

---

## How to Test

1. Register a user with `role=admin` (or update an existing user in SQLite directly)
2. Log in → see the bottom tab bar with "Chats" and "Admin" tabs
3. Admin tab → tap HR → document list (empty)
4. Tap "+ Upload" → pick a PDF → tap "Upload & Index" → success screen
5. Back to document list → pull to refresh → document appears with chunk count
6. Tap the delete icon → confirm → document disappears
7. Log in as a regular user → no Admin tab visible, just the chat interface
