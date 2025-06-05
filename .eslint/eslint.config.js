/*
SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
SPDX-License-Identifier: MPL-2.0
*/
// https://eslint.org/docs/latest/use/configure/
// eslint.config.js
import js from "@eslint/js";
import globals from "globals";

export default [
    {
        languageOptions: {
            globals: {
                ...globals.browser,
                commonjs: true,
                es6: true,
                jquery: true,
                $: 'readonly',
                bootstrap: 'readonly',
            },
            ecmaVersion: "latest",
            sourceType: "module",
        },
        rules: {
            "no-case-declarations": "off",
            "no-global-assign": "off",
        }
    },
];
