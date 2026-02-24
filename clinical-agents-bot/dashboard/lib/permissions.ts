import type { UserRole } from "@/lib/types";

export interface PermissionSet {
  canReadEhr: boolean;
  canCreatePatient: boolean;
  canWriteMeds: boolean;
  canWriteAllergiesLabsEncountersDocs: boolean;
  canWriteProblems: boolean;
  canWriteImaging: boolean;
  canManageRelations: boolean;
  canListAllRelations: boolean;
  canListUsers: boolean;
  canManageUsers: boolean;
}

const MAP: Record<UserRole, PermissionSet> = {
  admin: {
    canReadEhr: true,
    canCreatePatient: true,
    canWriteMeds: true,
    canWriteAllergiesLabsEncountersDocs: true,
    canWriteProblems: true,
    canWriteImaging: true,
    canManageRelations: true,
    canListAllRelations: true,
    canListUsers: true,
    canManageUsers: true,
  },
  physician: {
    canReadEhr: true,
    canCreatePatient: true,
    canWriteMeds: true,
    canWriteAllergiesLabsEncountersDocs: true,
    canWriteProblems: true,
    canWriteImaging: true,
    canManageRelations: true,
    canListAllRelations: false,
    canListUsers: false,
    canManageUsers: false,
  },
  nurse: {
    canReadEhr: true,
    canCreatePatient: false,
    canWriteMeds: false,
    canWriteAllergiesLabsEncountersDocs: true,
    canWriteProblems: false,
    canWriteImaging: false,
    canManageRelations: false,
    canListAllRelations: false,
    canListUsers: false,
    canManageUsers: false,
  },
  staff: {
    canReadEhr: true,
    canCreatePatient: false,
    canWriteMeds: false,
    canWriteAllergiesLabsEncountersDocs: false,
    canWriteProblems: false,
    canWriteImaging: false,
    canManageRelations: false,
    canListAllRelations: false,
    canListUsers: false,
    canManageUsers: false,
  },
};

export function getPermissions(role: UserRole): PermissionSet {
  return MAP[role];
}
