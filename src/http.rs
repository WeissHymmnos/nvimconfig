use crate::model::{
    AddKeymapRequest, AddOptionRequest, AddPluginRequest, ApiError, BatchPatchRequest, ChangeEvent,
    DeleteEntityRequest, PatchRequest, RollbackRequest, StateResponse,
};
use crate::state::AppState;
use axum::extract::{Path, Query, State};
use axum::http::{header, Request, StatusCode};
use axum::middleware::{self, Next};
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::{IntoResponse, Response};
use axum::routing::{delete, get, patch, post};
use axum::{Json, Router};
use futures_util::stream::Stream;
use serde::Deserialize;
use serde_json::json;
use std::convert::Infallible;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::broadcast;

#[derive(Debug, Default, Deserialize)]
struct DeleteQuery {
    #[serde(default)]
    file: Option<String>,
    #[serde(default, alias = "expected_revision")]
    revision: Option<String>,
}

#[derive(Debug, Default, Deserialize)]
struct OptionalDeleteBody {
    #[serde(default)]
    file: Option<String>,
    #[serde(default, alias = "expected_revision")]
    revision: Option<String>,
}

pub fn router(state: Arc<AppState>) -> Router {
    let authenticated = Router::new()
        .route("/api/state", get(get_state))
        .route("/api/schema", get(get_schema))
        .route("/api/entities", patch(patch_entity).delete(delete_entity_body))
        .route("/api/entities/batch", patch(patch_entities_batch))
        .route("/api/keymaps/batch", patch(patch_entities_batch))
        .route("/api/plugins/batch", patch(patch_entities_batch))
        // DELETE /api/entities/:id
        .route("/api/entities/{id}", delete(delete_entity_by_id))
        .route("/api/rollback", post(rollback_config))
        .route("/api/options", post(add_option))
        .route("/api/keymaps", post(add_keymap))
        .route("/api/plugins", post(add_plugin))
        .route("/api/events", get(get_events))
        .route_layer(middleware::from_fn_with_state(state.clone(), authorize));
    Router::new()
        .route("/api/health", get(health))
        .merge(authenticated)
        .with_state(state)
}

async fn health() -> Json<serde_json::Value> {
    Json(json!({"ok": true}))
}

async fn get_state(State(state): State<Arc<AppState>>) -> Json<StateResponse> {
    Json(StateResponse {
        snapshot: state.snapshot().await,
        nvim: state.nvim_status().await,
    })
}

async fn get_schema(State(state): State<Arc<AppState>>) -> Json<serde_json::Value> {
    Json(state.schema().await)
}

async fn patch_entity(
    State(state): State<Arc<AppState>>,
    Json(request): Json<PatchRequest>,
) -> Result<Json<crate::model::PatchResponse>, ApiError> {
    state.patch(request).await.map(Json)
}

async fn patch_entities_batch(
    State(state): State<Arc<AppState>>,
    Json(request): Json<BatchPatchRequest>,
) -> Result<Json<crate::model::PatchResponse>, ApiError> {
    state.patch_batch(request).await.map(Json)
}

async fn delete_entity_body(
    State(state): State<Arc<AppState>>,
    Json(request): Json<DeleteEntityRequest>,
) -> Result<Json<crate::model::PatchResponse>, ApiError> {
    state.delete_entity(request).await.map(Json)
}

async fn delete_entity_by_id(
    State(state): State<Arc<AppState>>,
    Path(id): Path<String>,
    Query(query): Query<DeleteQuery>,
    body: axum::body::Bytes,
) -> Result<Json<crate::model::PatchResponse>, ApiError> {
    let parsed_body = if body.is_empty() {
        OptionalDeleteBody::default()
    } else {
        serde_json::from_slice::<OptionalDeleteBody>(&body).unwrap_or_default()
    };
    state
        .delete_entity(DeleteEntityRequest {
            id,
            file: query.file.or(parsed_body.file),
            revision: query.revision.or(parsed_body.revision),
        })
        .await
        .map(Json)
}

async fn rollback_config(
    State(state): State<Arc<AppState>>,
    body: axum::body::Bytes,
) -> Result<Json<crate::model::PatchResponse>, ApiError> {
    let request = if body.is_empty() {
        RollbackRequest {
            file: None,
            target_revision: None,
        }
    } else {
        serde_json::from_slice::<RollbackRequest>(&body)
            .map_err(|err| ApiError::BadRequest(format!("invalid rollback request: {err}")))?
    };
    state.rollback(request).await.map(Json)
}

async fn add_option(
    State(state): State<Arc<AppState>>,
    Json(request): Json<AddOptionRequest>,
) -> Result<Json<crate::model::PatchResponse>, ApiError> {
    state.add_option(request).await.map(Json)
}

async fn add_keymap(
    State(state): State<Arc<AppState>>,
    Json(request): Json<AddKeymapRequest>,
) -> Result<Json<crate::model::PatchResponse>, ApiError> {
    state.add_keymap(request).await.map(Json)
}

async fn add_plugin(
    State(state): State<Arc<AppState>>,
    Json(request): Json<AddPluginRequest>,
) -> Result<Json<crate::model::PatchResponse>, ApiError> {
    state.add_plugin(request).await.map(Json)
}

async fn get_events(
    State(state): State<Arc<AppState>>,
) -> Sse<impl Stream<Item = Result<Event, Infallible>>> {
    let mut receiver = state.subscribe();
    let stream = async_stream::stream! {
        yield Ok(Event::default().event("connected").data("{}"));
        loop {
            match receiver.recv().await {
                Ok(change) => yield Ok(change_event(change)),
                Err(broadcast::error::RecvError::Lagged(_)) => {
                    yield Ok(change_event(ChangeEvent { reason: "events_lagged".to_owned() }));
                }
                Err(broadcast::error::RecvError::Closed) => break,
            }
        }
    };
    Sse::new(stream).keep_alive(
        KeepAlive::new()
            .interval(Duration::from_secs(15))
            .text("keep-alive"),
    )
}

fn change_event(change: ChangeEvent) -> Event {
    Event::default().event("change").data(
        serde_json::to_string(&change).unwrap_or_else(|error| {
            format!("{{\"reason\":\"event serialization failed: {error}\"}}")
        }),
    )
}

async fn authorize(
    State(state): State<Arc<AppState>>,
    request: Request<axum::body::Body>,
    next: Next,
) -> Response {
    let bearer = request
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "));
    let query_token = if request.uri().path() == "/api/events" {
        request.uri().query().and_then(|query| {
            query.split('&').find_map(|part| {
                part.strip_prefix("token=")
                    .filter(|_| !part[6..].contains('='))
            })
        })
    } else {
        None
    };
    if bearer == Some(state.token.as_str()) || query_token == Some(state.token.as_str()) {
        next.run(request).await
    } else {
        (
            StatusCode::UNAUTHORIZED,
            Json(json!({
                "error": {
                    "code": "unauthorized",
                    "message": "a valid Authorization Bearer token is required (or token query for SSE)"
                }
            })),
        )
            .into_response()
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let (status, code) = match self {
            ApiError::BadRequest(_) => (StatusCode::BAD_REQUEST, "bad_request"),
            ApiError::Conflict(_) => (StatusCode::CONFLICT, "revision_conflict"),
            ApiError::NotFound(_) => (StatusCode::NOT_FOUND, "not_found"),
            ApiError::Internal(_) => (StatusCode::INTERNAL_SERVER_ERROR, "internal_error"),
        };
        (
            status,
            Json(json!({
                "error": {
                    "code": code,
                    "message": self.to_string()
                }
            })),
        )
            .into_response()
    }
}
