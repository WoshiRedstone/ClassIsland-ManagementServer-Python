import { h } from 'vue';
import { NAvatar, NTag } from 'naive-ui';
import ClientGroupIndicator from '@/components/ClientGroupIndicator/index.vue';
import { BasicColumn } from '@/components/Table';
import {AbstractClient, Client} from "@/api/globals";

export const columns: BasicColumn<AbstractClient>[] = [
  {
    title: 'ID',
    key: 'id',
  },
  {
    'title': '分组',
    'key': 'group',
    render(data) {
      return h(ClientGroupIndicator, {
        group: data.group,
      });
    }
  },
  {
    title: '创建时间',
    key: 'createdTime'
  }
];
