/* Copyright 2017-present, The Visdom Authors */
import { useEffect } from 'react';

export const APP_NAME = 'Visdom';

export const formatPageTitle = (title) => (title ? `${title} · ${APP_NAME}` : APP_NAME);

// Sets the browser tab title while the calling page is mounted and puts the
// previous title back when it unmounts.
const usePageTitle = (title) => {
  useEffect(() => {
    const previous = document.title;
    document.title = formatPageTitle(title);
    return () => {
      document.title = previous;
    };
  }, [title]);
};

export default usePageTitle;
