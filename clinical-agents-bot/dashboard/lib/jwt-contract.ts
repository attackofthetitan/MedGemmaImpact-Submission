export const JWT_ALGORITHM = "HS256";
export const DEFAULT_TOKEN_EXPIRE_MINUTES = 480;

export type JwtClaims = {
  sub: string;
  username: string;
  role: "admin" | "physician" | "nurse" | "staff";
  iat: number;
  exp: number;
};

