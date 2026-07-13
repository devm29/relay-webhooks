const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString("base64url")

export function fakeJwt(claims: Record<string, unknown>): string {
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode(claims)}.signature`
}

export const liveJwt = () => fakeJwt({ sub: "usr_1", exp: Math.floor(Date.now() / 1000) + 3600 })
export const expiredJwt = () => fakeJwt({ sub: "usr_1", exp: Math.floor(Date.now() / 1000) - 60 })
