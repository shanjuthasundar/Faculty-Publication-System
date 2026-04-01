function createStore(reducer, initialState) {
  let state = initialState;
  const listeners = new Set();

  return {
    getState() {
      return state;
    },
    dispatch(action) {
      state = reducer(state, action);
      listeners.forEach((listener) => listener(state, action));
      return action;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }
  };
}

const initialAppState = {
  faculty: null,
  publications: [],
  pagination: {
    page: 1,
    pageSize: 8,
    total: 0,
    totalPages: 1
  },
  stats: {
    total: 0,
    journals: 0,
    conferences: 0,
    nationalConferences: 0,
    internationalConferences: 0,
    scopusIndexed: 0,
    nonScopusIndexed: 0,
    sciIndexed: 0,
    nonSciIndexed: 0,
    indexedBookChapters: 0,
    nonIndexedBookChapters: 0
  }
};

function appReducer(state, action) {
  switch (action.type) {
    case "SET_FACULTY":
      return { ...state, faculty: action.payload };
    case "SET_PUBLICATIONS":
      return { ...state, publications: Array.isArray(action.payload) ? action.payload : [] };
    case "SET_STATS":
      return { ...state, stats: action.payload || state.stats };
    case "SET_PAGINATION":
      return { ...state, pagination: action.payload || state.pagination };
    case "RESET_APP":
      return { ...initialAppState };
    default:
      return state;
  }
}

export const store = createStore(appReducer, initialAppState);
window.appStore = store;
