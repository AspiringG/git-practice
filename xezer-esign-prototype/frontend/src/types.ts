export type Role = "HR_EMPLOYEE" | "HR_MANAGER" | "WAREHOUSE_OPERATOR";
export type Status = "DRAFT" | "WAITING_FOR_SIGNATURES" | "SIGNED" | "RELEASED" | "CANCELLED";
export type StepRole = "RECIPIENT" | "HR_MANAGER" | "WAREHOUSE_OPERATOR";

export interface User {
  id: number;
  full_name: string;
  role: Role;
  title: string;
  department_code: string;
}

export interface Recipient extends User {
  department_name: string;
}

export interface Equipment {
  asset_code: string;
  category: "PRIBOR" | "LAMP";
  type_name: string;
  power: string;
  location: string;
  description: string;
  availability: "AVAILABLE" | "RESERVED" | "ISSUED";
  holder_name: string | null;
  issued_document_number: string | null;
  reserved_document_number: string | null;
}

export interface DocumentSummary {
  id: number;
  document_number: string;
  status: Status;
  recipient_name: string;
  recipient_title: string;
  department_code: string;
  department_name: string;
  purpose: string;
  asset_codes: string[];
  signed_count: number;
  required_count: number;
  next_signer_name: string | null;
  next_signer_role: string | null;
  awaiting_me: boolean;
  created_at: string;
  updated_at: string;
  issue_date: string;
  released_at: string | null;
}

export interface Signature {
  id: number;
  signing_order: number;
  signer_user_id: number;
  signer_name: string;
  signer_role: StepRole;
  signer_role_label: string;
  signer_title: string;
  signed_at: string;
  document_hash: string;
  document_revision: number;
  method: "INTERNAL_PIN";
  invalidated_at: string | null;
  invalidation_reason: string | null;
}

export interface Signer {
  signing_order: number;
  role: StepRole;
  role_label: string;
  user: { id: number; full_name: string; title: string };
  state: "SIGNED" | "NEXT" | "PENDING";
  signature: Signature | null;
}

export interface AuditEvent {
  id: number;
  event_type: string;
  occurred_at: string;
  description: string;
  actor_name: string | null;
  actor_title: string | null;
  detail: string | null;
}

export interface DocumentItem {
  line_no: number;
  asset_code: string;
  category: "PRIBOR" | "LAMP";
  description: string;
  type_name: string;
  power: string;
}

export interface DocumentDetail {
  id: number;
  document_number: string;
  doc_type: string;
  type_label: string;
  type_label_az: string;
  status: Status;
  revision: number;
  recipient: User;
  department: { code: string; name: string };
  purpose: string;
  issue_date: string;
  expected_return_date: string;
  notes: string;
  created_by: User;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  signed_at: string | null;
  released_at: string | null;
  released_by: User | null;
  cancelled_at: string | null;
  cancelled_by: User | null;
  cancel_reason: string | null;
  payload_hash: string | null;
  payload_snapshot: string | null;
  integrity: "VERIFIED" | "MISMATCH" | "NOT_SUBMITTED";
  items: DocumentItem[];
  signers: Signer[];
  signed_count: number;
  required_count: number;
  invalidated_signatures: Signature[];
  events: AuditEvent[];
  actions: {
    can_edit: boolean;
    can_submit: boolean;
    can_reopen: boolean;
    reopen_invalidates: number;
    can_cancel: boolean;
    is_signer: boolean;
    my_step_state: Signer["state"] | null;
    can_sign: boolean;
    sign_blocked_reason: string | null;
    can_release: boolean;
    release_blocked_reason: string | null;
    next_signer: { user_id: number; full_name: string; role_label: string } | null;
  };
}

export interface DocumentInput {
  recipient_user_id: number;
  purpose: string;
  issue_date: string;
  expected_return_date: string;
  notes: string;
  equipment_codes: string[];
}
