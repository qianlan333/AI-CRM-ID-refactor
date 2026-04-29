(function (window) {
  "use strict";

  function safeJsonParse(text) {
    try {
      return JSON.parse(text);
    } catch (_error) {
      return null;
    }
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function headersToObject(headers) {
    const result = {};
    if (!headers) return result;
    if (typeof Headers !== "undefined" && headers instanceof Headers) {
      headers.forEach((value, key) => {
        result[key] = value;
      });
      return result;
    }
    return { ...headers };
  }

  function hasHeader(headers, name) {
    const normalizedName = String(name || "").toLowerCase();
    return Object.keys(headers).some((key) => key.toLowerCase() === normalizedName);
  }

  function hasBody(options) {
    return Object.prototype.hasOwnProperty.call(options, "body") && options.body !== undefined && options.body !== null;
  }

  function isFormData(value) {
    return typeof FormData !== "undefined" && value instanceof FormData;
  }

  function isJsonBody(value) {
    return Array.isArray(value) || Object.prototype.toString.call(value) === "[object Object]";
  }

  function buildRequestOptions(options) {
    const finalOptions = { ...options };
    const headers = headersToObject(options.headers);
    if (!hasHeader(headers, "Accept")) {
      headers.Accept = "application/json";
    }

    if (hasBody(options) && !isFormData(options.body)) {
      if (!hasHeader(headers, "Content-Type")) {
        headers["Content-Type"] = "application/json";
      }
      if (isJsonBody(options.body)) {
        finalOptions.body = JSON.stringify(options.body);
      }
    }

    finalOptions.headers = headers;
    finalOptions.credentials = "same-origin";
    return finalOptions;
  }

  function buildRequestError(response, payload) {
    const error = new Error((payload && payload.error) || "request failed");
    error.status = response.status;
    error.payload = payload;
    return error;
  }

  function requestJson(url, options = {}) {
    const finalOptions = buildRequestOptions(options);
    return fetch(url, finalOptions)
      .then((response) =>
        response.text().then((text) => ({
          response,
          payload: text ? safeJsonParse(text) : null,
        })),
      )
      .then(({ response, payload }) => {
        if (!response.ok || (payload && payload.ok === false)) {
          throw buildRequestError(response, payload);
        }
        return payload || { ok: true };
      });
  }

  function isPermissionError(error) {
    const message = String((error && error.message) || "");
    return Boolean(error) && (error.status === 401 || error.status === 403 || message.includes("令牌无效"));
  }

  window.AdminApi = {
    ...(window.AdminApi || {}),
    safeJsonParse,
    escapeHtml,
    requestJson,
    isPermissionError,
  };
})(window);
