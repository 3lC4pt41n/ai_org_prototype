module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'body-max-line-length': [2, 'always', 120],
    'subject-case': [2, 'never', ['sentence-case']]
  }
};
