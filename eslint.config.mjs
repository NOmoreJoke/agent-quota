import tseslint from "@typescript-eslint/eslint-plugin";
import parser from "@typescript-eslint/parser";

const timerReason =
  "Imperative timers/frame schedulers are forbidden in UI views; move audited interaction timing into controlled src/hooks/ modules.";

export default [
  { ignores: ["dist/**", "src-tauri/target/**", "coverage/**", "output/**", "artifacts/**"] },
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser,
      parserOptions: { ecmaVersion: 2024, sourceType: "module", ecmaFeatures: { jsx: true } },
    },
    plugins: { "@typescript-eslint": tseslint },
    rules: {
      "no-eval": "error",
      "no-implied-eval": "error",
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "@typescript-eslint/ban-ts-comment": [
        "error",
        {
          "ts-ignore": true,
          "ts-nocheck": true,
          "ts-expect-error": "allow-with-description",
          minimumDescriptionLength: 10,
        },
      ],
    },
  },
  {
    files: ["src/contracts/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["../host/*", "../hooks/*", "../ui/*", "@tauri-apps/*"],
              message: "src/contracts/ is a pure leaf schema layer and must not import host, hooks, UI, or Tauri runtime APIs.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/host/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["../hooks/*", "../ui/*"],
              message: "src/host/ must only depend on src/contracts/ and Tauri IPC APIs, never hooks or UI components.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/ui/**/*.{ts,tsx}"],
    ignores: ["src/ui/**/*.test.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "react",
              importNames: ["useEffect", "useLayoutEffect"],
              message: "Raw useEffect/useLayoutEffect is forbidden in src/ui/; encapsulate side effects inside controlled src/hooks/ modules.",
            },
          ],
          patterns: [
            {
              group: ["@tauri-apps/*"],
              message: "src/ui/ must not import @tauri-apps/* directly; route through src/host/ or src/hooks/.",
            },
          ],
        },
      ],
      "no-restricted-globals": [
        "error",
        { name: "setTimeout", message: timerReason },
        { name: "setInterval", message: timerReason },
        { name: "requestAnimationFrame", message: timerReason },
        { name: "requestIdleCallback", message: timerReason },
      ],
      "no-restricted-properties": [
        "error",
        { object: "window", property: "setTimeout", message: timerReason },
        { object: "window", property: "setInterval", message: timerReason },
        { object: "window", property: "requestAnimationFrame", message: timerReason },
        { object: "window", property: "requestIdleCallback", message: timerReason },
        { object: "globalThis", property: "setTimeout", message: timerReason },
        { object: "globalThis", property: "setInterval", message: timerReason },
      ],
    },
  },
];
