"use strict";

import {
  CANDIDATE_REVIEW_ELEMENT_IDS,
  mountCandidateReview,
} from "./candidate-review-markup.js";

const REQUIRED_ELEMENT_IDS = [
  "projectSelect", "refreshProjectsBtn", "workflowNav", "saveBtn",
  "saveIndicator", "saveIndicatorText", "globalAlert", "globalAlertText",
  "dismissAlertBtn", "layerCounter", "layerSearch", "clearSearchBtn",
  "showAllLayersBtn", "hideAllLayersBtn", "visibleLayerCount", "layerList",
  "layerModeBtn", "jointModeBtn", "toggleCompositeBtn", "toggleSkeletonBtn",
  "previewOpacity", "previewOpacityValue", "zoomOutBtn", "zoomInBtn",
  "zoomValueBtn", "fitCanvasBtn", "canvasViewport", "canvasSpace",
  "canvasSurface", "compositeImage", "layerStack", "skeletonSvg", "boneGroup",
  "layerSelectionGroup", "geometryEvidenceGroup", "candidateGroup", "jointGroup", "canvasEmpty",
  "canvasEmptyTitle", "canvasEmptyText", "canvasLoading", "revisionBadge",
  "layerInspector", "layerConfidence", "layerSelectionEmpty", "layerFields",
  "layerSwatch", "selectedLayerName", "selectedLayerId", "selectedLayerBbox",
  "selectedLayerState", "semanticRoleInput", "semanticSideSelect",
  "layerDispositionSelect", "selectedLayerVisible", "jointConfidence",
  "jointSelectionEmpty", "jointFields", "selectedJointName", "selectedJointState",
  "jointXInput", "jointYInput", "resetJointBtn",
  ...CANDIDATE_REVIEW_ELEMENT_IDS,
  "qaCounter", "qaList",
  "capabilityList", "overrideNotes", "canvasStatus", "selectionStatus",
  "overrideStatus", "networkStatus", "liveRegion", "conflictActions",
  "exportLocalPatchBtn", "replayConflictBtn",
];

export function collectRequiredElements(root = document) {
  mountCandidateReview(root);
  const elements = {};
  for (const id of REQUIRED_ELEMENT_IDS) {
    const element = root.getElementById(id);
    if (!element) throw new Error(`Missing required DOM element: ${id}`);
    elements[id] = element;
  }
  return elements;
}

export { REQUIRED_ELEMENT_IDS };
