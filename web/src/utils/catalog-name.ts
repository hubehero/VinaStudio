const CJK = /[\u3400-\u9fff]/

export function chineseAlias(aliases: readonly string[] | null | undefined): string | null {
  return aliases?.find((alias) => CJK.test(alias)) ?? null
}
